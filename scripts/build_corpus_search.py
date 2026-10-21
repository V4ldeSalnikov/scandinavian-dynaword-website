#!/usr/bin/env python3
"""Build complete keyword/POTION indexes on a mounted, pinned HF dataset.

Run one bounded CPU Job per language. Source commits are resumable; publication
requires exact record counts and matching annotation identities. A ready
manifest is written last, after full index validation and a retrieval benchmark.
"""
import argparse
from bisect import bisect_right
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import faiss
from faiss.contrib.ondisk import merge_ondisk
import numpy as np
import pyarrow.parquet as pq
import tantivy
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.corpus_search import FIELDS, METADATA_DTYPE, MODEL_REVISION, encode_documents, schema


def write_json(path, value):
    temporary = path.with_suffix('.partial.json')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    temporary.replace(path)


def metadata_rows(source, start, raw_rows, annotation_entry, annotation_array):
    records = np.zeros(len(raw_rows), dtype=METADATA_DTYPE)
    labels = []
    for offset, raw in enumerate(raw_rows):
        token_count = raw['token_count']
        if not isinstance(token_count, int) or not 0 <= token_count < 2**32:
            raise ValueError('Invalid token count')
        records[offset]['tokens'] = token_count
        values = {}
        if annotation_array is not None:
            annotation = annotation_array[source['offset'] + start + offset]
            expected = int.from_bytes(hashlib.blake2b(raw['id'].encode(), digest_size=8).digest(), 'little')
            if int(annotation['id_hash']) != expected or int(annotation['tokens']) != token_count:
                raise ValueError(f"Annotation identity differs: {source['id']} row {start + offset}")
            for field in FIELDS:
                code = int(annotation[field]); records[offset][field] = code
                values[field] = next((name for name, n in annotation_entry['labels'][field].items() if n == code), None)
        labels.append(values)
    return records, labels


def source_files(input_dir, data):
    card = (input_dir / 'README.md').read_text()
    configs = yaml.safe_load(card.split('---')[1])['configs']
    result = {}
    for config in configs:
        name = config['config_name']
        if name not in {s['id'] for s in data['sources']}:
            continue
        files = []
        for split in config['data_files']:
            if split['split'] != 'train':
                raise ValueError('Unexpected dataset split')
            patterns = split['path'] if isinstance(split['path'], list) else [split['path']]
            for pattern in patterns:
                files.extend(input_dir.glob(pattern))
        result[name] = sorted(set(files))
        if not result[name]:
            raise ValueError(f'No original files for {name}')
    if set(result) != {s['id'] for s in data['sources']}:
        raise ValueError('Dataset configurations and catalog sources differ')
    return result


def build(args):
    from model2vec import StaticModel
    data = next(d for d in json.loads(args.catalog.read_text())['datasets'] if d['id'] == args.language)
    folder = args.output / data['id'] / data['revision']
    folder.mkdir(parents=True, exist_ok=True)
    state_path = folder / 'progress.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        'format': 1, 'status': 'building', 'revision': data['revision'], 'model_revision': MODEL_REVISION,
        'language': data['id'], 'completed_sources': [], 'ann_sources': [], 'records': 0,
        'vectors': 0, 'sources': [], 'labels': {f: {} for f in FIELDS},
    }
    if state['revision'] != data['revision'] or state['model_revision'] != MODEL_REVISION:
        raise ValueError('Build configuration changed; use a new output directory')
    if (folder / 'manifest.json').exists():
        print('Already complete', flush=True); return
    source_list = []
    offset = 0
    for source in sorted(data['sources'], key=lambda s: s['id']):
        source_list.append({**source, 'offset': offset})
        offset += source['records']
    assert offset == data['records']
    paths = source_files(args.input, data)
    annotation_entry = annotation_array = None
    if data['annotation_distributions']:
        entry = json.loads((args.annotations / 'manifest.json').read_text())['languages'][data['id']]
        if entry['revision'] != data['revision'] or entry['records'] != data['records']:
            raise ValueError('Annotation release differs')
        annotation_entry = entry
        annotation_array = np.load(args.annotations / entry['path'], mmap_mode='r', allow_pickle=False)
        if [(s['id'], s['offset'], s['records']) for s in entry['sources']] != [(s['id'], s['offset'], s['records']) for s in source_list]:
            raise ValueError('Annotation source offsets differ')
        state['labels'] = entry['labels']
    model = StaticModel.from_pretrained(str(args.model))
    (folder / 'vectors').mkdir(exist_ok=True)
    (folder / 'metadata').mkdir(exist_ok=True)
    (folder / 'fulltext').mkdir(exist_ok=True)
    index = tantivy.Index.open(str(folder / 'fulltext')) if (folder / 'fulltext/meta.json').exists() else tantivy.Index(schema(), path=str(folder / 'fulltext'))
    writer = index.writer(heap_size=768_000_000, num_threads=4)
    for source in source_list:
        name = source['id']
        if name in state['completed_sources']:
            continue
        print(f'Indexing {name}: {source["records"]:,} records', flush=True)
        writer.delete_documents('source', name)
        vector_path, meta_path = folder / 'vectors' / f'{name}.f16', folder / 'metadata' / f'{name}.bin'
        count = covered = 0
        started = time.monotonic()
        with vector_path.with_suffix('.partial').open('wb') as vectors_out, meta_path.with_suffix('.partial').open('wb') as meta_out:
            for path in paths[name]:
                parquet = pq.ParquetFile(path)
                for batch in parquet.iter_batches(batch_size=256, columns=['id', 'text', 'token_count']):
                    rows = batch.to_pylist()
                    metadata, annotations = metadata_rows(source, count, rows, annotation_entry, annotation_array)
                    vectors = encode_documents(model, [row['text'] for row in rows])
                    covered += int(np.any(vectors, axis=1).sum())
                    vectors_out.write(vectors.astype('<f2').tobytes())
                    meta_out.write(metadata.tobytes())
                    for row, labels in zip(rows, annotations):
                        document = {'id': row['id'].encode('utf-8'), 'text': row['text'], 'source': name,
                                    'domain': source['domain'], 'record_no': source['offset'] + count,
                                    'row_index': count, 'token_count': row['token_count']}
                        document.update({field: labels.get(field) or '__missing__' for field in FIELDS})
                        writer.add_document(tantivy.Document.from_dict(document, index.schema))
                        count += 1
                    if count % 100_096 == 0:
                        print(f'  {name}: {count:,} in {time.monotonic() - started:.1f}s', flush=True)
        if count != source['records']:
            writer.rollback(); raise ValueError(f'{name}: indexed {count}, expected {source["records"]}')
        writer.commit()
        vector_path.with_suffix('.partial').replace(vector_path)
        meta_path.with_suffix('.partial').replace(meta_path)
        state['completed_sources'].append(name)
        state['records'] += count; state['vectors'] += covered
        state['sources'].append({'id': name, 'domain': source['domain'], 'offset': source['offset'], 'records': count, 'vectors': covered})
        write_json(state_path, state)
        print(f'Committed {name}: {state["records"]:,} / {data["records"]:,}', flush=True)
    writer.wait_merging_threads(); del writer
    index.reload()
    if index.searcher().num_docs != data['records'] or state['records'] != data['records']:
        raise ValueError('Full-text index is incomplete')
    with (folder / 'metadata.partial').open('wb') as target:
        for source in source_list:
            with (folder / 'metadata' / f'{source["id"]}.bin').open('rb') as source_file:
                while chunk := source_file.read(4 * 1024**2):
                    target.write(chunk)
    (folder / 'metadata.partial').replace(folder / 'metadata.bin')
    faiss.omp_set_num_threads(6)
    trained_path = folder / 'trained.faiss'
    if not trained_path.exists():
        nlist = min(16_384, max(64, 2 ** int(math.log2(max(64, data['records'] // 1000)))))
        rng = np.random.default_rng(20261022)
        selected = np.sort(rng.choice(data['records'], min(data['records'], max(40_000, 50 * nlist)), replace=False))
        samples = []
        for source in source_list:
            positions = selected[(selected >= source['offset']) & (selected < source['offset'] + source['records'])] - source['offset']
            matrix = np.memmap(folder / 'vectors' / f'{source["id"]}.f16', mode='r', dtype='<f2', shape=(source['records'], 256))
            samples.append(np.asarray(matrix[positions], dtype=np.float32))
        training = np.concatenate(samples)
        training = training[np.any(training, axis=1)]
        while nlist > 64 and len(training) < nlist * 39:
            nlist //= 2
        if len(training) < 256:
            raise ValueError('Insufficient usable vectors to train search')
        faiss.normalize_L2(training)
        print(f'Training IVF{nlist},PQ32 on {len(training):,} vectors', flush=True)
        trained = faiss.index_factory(256, f'IVF{nlist},PQ32', faiss.METRIC_INNER_PRODUCT)
        trained.train(training)
        faiss.write_index(trained, str(trained_path))
        del training, samples, matrix
    trained = faiss.read_index(str(trained_path))
    (folder / 'ann-parts').mkdir(exist_ok=True)
    for source in source_list:
        name = source['id']
        if name in state['ann_sources']:
            continue
        part = faiss.clone_index(trained)
        vectors = np.memmap(folder / 'vectors' / f'{name}.f16', mode='r', dtype='<f2', shape=(source['records'], 256))
        for start in range(0, len(vectors), 32_768):
            matrix = np.asarray(vectors[start:start + 32_768], dtype=np.float32)
            valid = np.any(matrix, axis=1); matrix = matrix[valid]
            identifiers = np.arange(source['offset'] + start, source['offset'] + start + len(valid), dtype=np.int64)[valid]
            faiss.normalize_L2(matrix)
            part.add_with_ids(matrix, identifiers)
        path = folder / 'ann-parts' / f'{name}.faiss'
        faiss.write_index(part, str(path.with_suffix('.partial')))
        path.with_suffix('.partial').replace(path)
        state['ann_sources'].append(name); write_json(state_path, state)
        print(f'Compressed vectors {name}: {part.ntotal:,}', flush=True)
        del part, vectors
    print('Merging vector partitions', flush=True)
    parts = [str(folder / 'ann-parts' / f'{s["id"]}.faiss') for s in source_list]
    merge_ondisk(trained, parts, str(folder / 'index.ivfdata'))
    if trained.ntotal != state['vectors']:
        raise ValueError('Merged semantic coverage differs')
    faiss.write_index(trained, str(folder / 'index.faiss'))
    # Validate every source's text count, original identities at boundaries, and
    # sampled approximate recall against exact scores before publishing.
    searcher = index.searcher()
    for source in source_list:
        count = searcher.search(tantivy.Query.term_query(index.schema, 'source', source['id']), limit=1, count=True).count
        if count != source['records']:
            raise ValueError('Source coverage differs after merging')
        for position in [source['offset'], source['offset'] + source['records'] - 1]:
            result = searcher.search(tantivy.Query.term_query(index.schema, 'record_no', position), limit=2, count=True)
            if result.count != 1:
                raise ValueError('Duplicate or missing record number')
    rng = np.random.default_rng(20261022)
    positions = rng.choice(data['records'], min(32, data['records']), replace=False)
    offsets = [s['offset'] for s in source_list]
    def read_vectors(identifiers):
        output = np.empty((len(identifiers), 256), dtype=np.float32)
        groups = {}
        for i, identifier in enumerate(identifiers):
            s = source_list[bisect_right(offsets, int(identifier)) - 1]
            groups.setdefault(s['id'], (s, []))[1].append((i, int(identifier) - s['offset']))
        for name, (s, items) in groups.items():
            matrix = np.memmap(folder / 'vectors' / f'{name}.f16', mode='r', dtype='<f2', shape=(s['records'], 256))
            for i, row in items:
                output[i] = matrix[row]
        faiss.normalize_L2(output)
        return output
    queries = read_vectors(positions)
    queries = queries[np.any(queries, axis=1)]
    validation_started = time.monotonic()
    trained.nprobe = min(64, trained.nlist)
    _, candidates = trained.search(queries, 50)
    best = []
    for query, identifiers in zip(queries, candidates):
        identifiers = identifiers[identifiers >= 0]
        best.append(float((read_vectors(identifiers) @ query).max()) if len(identifiers) else 0)
    recall = sum(value >= 0.98 for value in best) / max(1, len(best))
    validation = {'queries': len(best), 'self_retrieval_cosine_at_50': recall,
                  'minimum_best_cosine': min(best, default=0), 'seconds': time.monotonic() - validation_started}
    write_json(folder / 'validation.json', validation)
    if recall < 0.9:
        raise ValueError('Vector validation did not reach the required self-retrieval threshold')
    print('Validated', json.dumps(validation), flush=True)
    state['status'] = 'ready'
    state['model'] = 'minishlab/potion-multilingual-128M'
    state['dimensions'] = 256
    state['nlist'] = trained.nlist
    state['vector_format'] = 'IVF/PQ32 with original-text re-encoding for reranking'
    state['sources'].sort(key=lambda s: s['offset'])
    state['completed_at'] = time.time()
    write_json(folder / 'manifest.json', state)
    write_json(state_path, state)
    print(f'READY {data["id"]}: {state["records"]:,} text records, {state["vectors"]:,} usable vectors', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('language', choices=['norwegian', 'swedish', 'icelandic', 'faroese'])
    parser.add_argument('--input', type=Path, default=Path('/corpus'))
    parser.add_argument('--output', type=Path, default=Path('/data'))
    parser.add_argument('--model', type=Path, default=Path('/model'))
    parser.add_argument('--annotations', type=Path, default=Path('/annotations'))
    parser.add_argument('--catalog', type=Path, required=True)
    build(parser.parse_args())
