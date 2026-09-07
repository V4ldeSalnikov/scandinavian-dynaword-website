"""Build document vectors for the complete pinned corpus from stored originals.

The official fastText .vec file is sorted by frequency. Stream its first 100,000
entries; the remaining vocabulary is explicitly out of vocabulary in this MVP.
Source commits are resumable, and zero-vector coverage is reported separately.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import multiprocessing
import sys
import time

import duckdb
import numpy as np
import requests
import tantivy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.embeddings import CACHE, MODEL, Encoder

MODEL_URL = 'https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.da.300.vec.gz'


def initialize_worker():
    global WORKER_MODEL
    WORKER_MODEL = Encoder()


def encode_batch(batch):
    start, texts = batch
    return start, np.asarray([WORKER_MODEL.encode(text) for text in texts], dtype=np.float16)


def document_batches(searcher, hits, lookup, identifiers):
    texts, start, characters = [], 0, 0
    for i, (_, address) in enumerate(hits):
        document = searcher.doc(address).to_dict()
        identifier = document['key'][0].split('/', 1)[1]
        identifiers[i] = lookup.pop(identifier)
        text = document['text'][0]
        texts.append(text)
        characters += len(text)
        if len(texts) >= 64 or characters >= 2_000_000:
            yield start, texts
            start, texts, characters = i+1, [], 0
    if texts:
        yield start, texts


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def prepare_model():
    if (MODEL/'definition.json').exists():
        return json.loads((MODEL/'definition.json').read_text())
    MODEL.mkdir(exist_ok=True)
    words, vectors, seen = [], [], set()
    print('Downloading the 100,000 most frequent Danish fastText entries…', flush=True)
    with requests.get(MODEL_URL, stream=True, timeout=(20, 90)) as response:
        response.raise_for_status()
        with gzip.GzipFile(fileobj=response.raw) as stream:
            assert stream.readline().decode().strip() == '2000000 300'
            for rank in range(1, 100001):
                line = stream.readline().decode('utf8')
                word, numbers = line.rstrip().split(' ', 1)
                word = word.lower()
                if word in seen:
                    continue
                v = np.fromstring(numbers, sep=' ', dtype=np.float32)
                if v.shape != (300,):
                    raise ValueError('Invalid pretrained vector dimensions')
                norm = np.linalg.norm(v)
                if norm:
                    words.append(word)
                    vectors.append(v / norm * (rank / (rank + 500)))
                    seen.add(word)
    np.save(MODEL/'words.npy', np.asarray(vectors))
    write_json(MODEL/'words.json', words)
    definition = {
        'name': 'Danish fastText word-vector baseline', 'dimensions': 300,
        'url': MODEL_URL, 'vocabulary_entries_read': 100000, 'vocabulary_size': len(words),
        'license': 'CC BY-SA 3.0',
        'attribution': 'Grave, Bojanowski, Gupta, Joulin, Mikolov (2018), Learning Word Vectors for 157 Languages',
        'method': 'Lowercase Unicode words; normalized word vectors weighted by rank/(rank+500); count-weighted sum over all original text; L2 normalization; float16 storage; cosine retrieval.',
        'matrix_sha256': hashlib.sha256((MODEL/'words.npy').read_bytes()).hexdigest(),
    }
    write_json(MODEL/'definition.json', definition)
    return definition


def main(workers=3):
    definition = prepare_model()
    manifest = json.loads((CACHE/'manifest.json').read_text())
    if manifest['status'] != 'ready':
        raise RuntimeError('Run metadata preparation first')
    with (CACHE/'corpus.duckdb').open('rb') as corpus_file:
        fingerprint = hashlib.file_digest(corpus_file, 'sha256').hexdigest()
    folder = CACHE/'semantic'
    folder.mkdir(exist_ok=True)
    state_path = CACHE/'semantic_manifest.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        'revision': manifest['revision'], 'status': 'building', 'sources': [],
        'records_processed': 0, 'records_with_vectors': 0, 'model': definition,
        'metadata_fingerprint': fingerprint,
    }
    if state.get('metadata_fingerprint') != fingerprint:
        raise RuntimeError('Metadata row identities have changed; rebuild the semantic directory and manifest.')
    if state['revision'] != manifest['revision'] or state['model'] != definition:
        raise RuntimeError('Semantic index revision/model mismatch; use a new cache')
    c = duckdb.connect(str(CACHE/'corpus.duckdb'), read_only=True)
    c.execute("SET memory_limit='2GB'; SET threads=2")
    index = tantivy.Index.open(str(CACHE/'fulltext'))
    # Batches bound queued text size; each worker loads the same frozen model.
    # Using processes lets long-document tokenization use more than one CPU.
    pool = multiprocessing.get_context('spawn').Pool(workers, initializer=initialize_worker)
    pending = {s['id']: s for s in manifest['sources'] if s['id'] not in state['sources']}
    while pending:
        text_state = json.loads((CACHE/'search_manifest.json').read_text())
        available = [s for s in pending.values() if s['id'] in text_state['sources']]
        if not available:
            print('Waiting for remaining original texts…', flush=True)
            time.sleep(10)
            continue
        source = min(available, key=lambda s: s['tokens'])
        name, expected = source['id'], source['records']
        print(f'Embedding {name}: {expected:,} records…', flush=True)
        started = time.time()
        lookup = dict(c.execute('SELECT id,record_no FROM records WHERE source=?', [name]).fetchall())
        if len(lookup) != expected:
            raise RuntimeError('Duplicate or missing source IDs')
        index.reload()
        searcher = index.searcher()
        result = searcher.search(tantivy.Query.term_query(index.schema, 'source', name), limit=expected, count=True)
        if result.count != expected:
            raise RuntimeError(f'{name}: original-text index count does not match metadata')
        vectors = np.lib.format.open_memmap(folder/f'{name}.partial.npy', mode='w+', dtype=np.float16, shape=(expected, 300))
        identifiers = np.empty(expected, dtype=np.int64)
        covered = 0
        report_at = 100000
        batches = document_batches(searcher, result.hits, lookup, identifiers)
        for start, batch in pool.imap(encode_batch, batches, chunksize=1):
            vectors[start:start+len(batch)] = batch
            covered += int(np.count_nonzero(np.any(batch, axis=1)))
            if start+len(batch) >= report_at:
                print(f'  {name}: {start+len(batch):,} records in {time.time()-started:.0f}s', flush=True)
                report_at += 100000
        if lookup:
            raise RuntimeError('Original text coverage incomplete')
        vectors.flush()
        del vectors, result, lookup, searcher
        (folder/f'{name}.partial.npy').replace(folder/f'{name}.npy')
        np.save(folder/f'{name}.ids.npy', identifiers)
        state['sources'].append(name)
        state['records_processed'] += expected
        state['records_with_vectors'] += covered
        write_json(state_path, state)
        del pending[name]
        print(f"[{len(state['sources'])}/50] {name}: {covered:,} usable vectors, {time.time()-started:.0f}s", flush=True)
    if state['records_processed'] != manifest['records']:
        raise RuntimeError('Semantic processing count differs from complete corpus')
    state['status'] = 'ready'
    write_json(state_path, state)
    pool.close()
    pool.join()
    print(f"READY: processed all {state['records_processed']:,} records; {state['records_with_vectors']:,} usable vectors", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=3)
    main(parser.parse_args().workers)
