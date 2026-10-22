"""Complete, revision-pinned text and vector search for the additional corpora.

The serving process only opens snapshots with a validated ready manifest. Build
jobs write a separate progress file, so partial indexes never become searchable.
"""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

import faiss
import numpy as np
import tantivy
from . import remote_ann

ROOT = Path(os.environ.get('DYNAWORD_SEARCH_ROOT', '/search-index'))
MODEL_ROOT = Path(os.environ.get('DYNAWORD_MODEL_ROOT', '/search-model'))
MODEL_REVISION = '73908c3438cf03b6a01bcb9611d62b23d0726f08'
FIELDS = ('content_quality', 'pii_presence', 'content_integrity', 'content_ratio',
          'content_length', 'information_density', 'educational_value',
          'reasoning_indicators', 'content_safety')
METADATA_DTYPE = np.dtype([('tokens', '<u4')] + [(field, 'u1') for field in FIELDS])
SEARCH_LOCK = threading.Semaphore(2)
READER_ROOT = tempfile.TemporaryDirectory(prefix='dynaword-search-readers-')


def reader_directory(path):
    """Keep Tantivy's reader locks local, with immutable data on the RO mount."""
    source = Path(path) / 'fulltext'
    identity = hashlib.sha256(str(source).encode()).hexdigest()[:24]
    target = Path(READER_ROOT.name) / identity
    target.mkdir(exist_ok=True)
    for entry in source.iterdir():
        if entry.is_file() and not entry.name.endswith('.lock'):
            link = target / entry.name
            try:
                link.symlink_to(entry.resolve())
            except FileExistsError:
                if not link.is_symlink() or link.resolve() != entry.resolve():
                    raise ValueError('Reader directory contains an unexpected file')
    return target


def schema():
    builder = tantivy.SchemaBuilder()
    builder.add_text_field('text', stored=True)
    builder.add_bytes_field('id', stored=True)
    builder.add_unsigned_field('record_no', stored=True, indexed=True, fast=True)
    builder.add_unsigned_field('row_index', stored=True)
    builder.add_unsigned_field('token_count', stored=True, indexed=True, fast=True)
    for field in ('source', 'domain') + FIELDS:
        builder.add_text_field(field, stored=True, tokenizer_name='raw', index_option='basic')
    return builder.build()


def directory(data):
    return ROOT / data['id'] / data['revision']


def status(data):
    path = directory(data) / 'manifest.json'
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return {'text': False, 'semantic': False, 'status': 'building'}
    valid = (state.get('format') == 1 and state.get('status') == 'ready'
             and state.get('revision') == data['revision']
             and state.get('records') == data['records']
             and state.get('model_revision') == MODEL_REVISION
             and sum(s['records'] for s in state.get('sources', [])) == data['records'])
    if not valid:
        return {'text': False, 'semantic': False, 'status': 'unavailable'}
    return {'text': True, 'semantic': True, 'status': 'ready',
            'records': state['records'], 'vectors': state['vectors'],
            'revision': data['revision'], 'model': 'minishlab/potion-multilingual-128M'}


@lru_cache(maxsize=4)
def snapshot(path):
    path = Path(path)
    state = json.loads((path / 'manifest.json').read_text())
    index = tantivy.Index.open(str(reader_directory(path)))
    if index.searcher().num_docs != state['records']:
        raise ValueError('Text index coverage does not match its manifest')
    metadata = np.memmap(path / 'metadata.bin', mode='r', dtype=METADATA_DTYPE)
    if len(metadata) != state['records']:
        raise ValueError('Metadata coverage does not match its manifest')
    return state, index, metadata


@lru_cache(maxsize=4)
def vector_index(path):
    index = faiss.read_index(str(Path(path) / 'index.faiss'),
                             faiss.IO_FLAG_SKIP_IVF_DATA | faiss.IO_FLAG_READ_ONLY | faiss.IO_FLAG_ONDISK_SAME_DIR)
    state = json.loads((Path(path) / 'manifest.json').read_text())
    if index.ntotal != state['vectors'] or index.d != 256:
        raise ValueError('Vector index coverage does not match its manifest')
    return index


@lru_cache(maxsize=1)
def encoder():
    from model2vec import StaticModel
    return StaticModel.from_pretrained(str(MODEL_ROOT))


def encode_documents(model, texts):
    """Bound tokenizer memory while representing every part of long records."""
    result = []
    for text in texts:
        if len(text) <= 100_000:
            result.append(None)
        else:
            parts = [text[i:i + 100_000] for i in range(0, len(text), 100_000)]
            total = np.zeros(256, dtype=np.float32)
            for part in parts:
                total += model.encode([part], max_length=None)[0] * len(part)
            result.append(total / max(float(np.linalg.norm(total)), 1e-12))
    pending, indices, characters = [], [], 0
    def flush():
        if pending:
            vectors = model.encode(pending, max_length=None)
            for i, vector in zip(indices, vectors):
                result[i] = vector
            pending.clear(); indices.clear()
    for i, text in enumerate(texts):
        if result[i] is not None:
            continue
        if characters + len(text) > 500_000 or len(pending) >= 256:
            flush(); characters = 0
        pending.append(text); indices.append(i); characters += len(text)
    flush()
    matrix = np.asarray(result, dtype=np.float32)
    return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)


def query_for(index, text, sources, annotations, bounds):
    clauses = [(tantivy.Occur.Must, index.parse_query(text, ['text']) if text else tantivy.Query.all_query())]
    clauses.append((tantivy.Occur.Must, tantivy.Query.term_set_query(index.schema, 'source', sorted(sources))))
    for key, value in annotations.items():
        clauses.append((tantivy.Occur.Must, tantivy.Query.term_query(index.schema, key, value)))
    if bounds:
        clauses.append((tantivy.Occur.Must, tantivy.Query.range_query(index.schema, 'token_count',
                       tantivy.FieldType.Unsigned, bounds.get('min_tokens'), bounds.get('max_tokens'))))
    return tantivy.Query.boolean_query(clauses)


def row_from_doc(document, score=None):
    doc = document.to_dict()
    row = {key: values[0] for key, values in doc.items() if key != 'text' and values}
    row['id'] = row['id'].decode('utf-8')
    for field in FIELDS:
        if row.get(field) == '__missing__':
            row[field] = None
    row.update(config=row['source'], preview=doc['text'][0][:700], text=None,
               annotations_available=any(row.get(k) is not None for k in FIELDS), text_truncated=False)
    if score is not None:
        row['score'] = float(score)
    return row


def text_search(data, text, sources, annotations, bounds, offset=0, limit=30):
    state, index, _ = snapshot(str(directory(data)))
    searcher = index.searcher()
    if not text and not annotations and not bounds:
        # Direct record-number lookups avoid sorting hundreds of millions of
        # rows just to render a page or jump to a row.
        remaining, identifiers = offset, []
        total = sum(s['records'] for s in state['sources'] if s['id'] in sources)
        for source in state['sources']:
            if source['id'] not in sources:
                continue
            if remaining >= source['records']:
                remaining -= source['records']; continue
            first = source['offset'] + remaining
            count = min(limit - len(identifiers), source['records'] - remaining)
            identifiers.extend(range(first, first + count)); remaining = 0
            if len(identifiers) >= limit:
                break
        rows = []
        for identifier in identifiers:
            result = searcher.search(tantivy.Query.term_query(index.schema, 'record_no', identifier), limit=1, count=False)
            if not result.hits:
                raise ValueError('Record missing from the complete index')
            rows.append(row_from_doc(searcher.doc(result.hits[0][1])))
        return {'rows': rows, 'total': total, 'has_more': offset + len(rows) < total, 'next_offset': offset + len(rows)}
    query = query_for(index, text, sources, annotations, bounds)
    options = {} if text else {'order_by_field': 'record_no', 'order': tantivy.Order.Asc}
    result = searcher.search(query, limit=limit, offset=offset, count=True, **options)
    rows = [row_from_doc(searcher.doc(address), score if text else None) for score, address in result.hits]
    return {'rows': rows, 'total': result.count, 'has_more': offset + len(rows) < result.count,
            'next_offset': offset + len(rows)}


def eligibility(state, metadata, sources, annotations, bounds):
    if len(sources) == len(state['sources']) and not annotations and not bounds:
        return None
    mask = np.zeros(state['records'], dtype=bool)
    for source in state['sources']:
        if source['id'] not in sources:
            continue
        first, last = source['offset'], source['offset'] + source['records']
        for start in range(first, last, 250_000):
            stop = min(start + 250_000, last)
            block = metadata[start:stop]
            selected = np.ones(stop - start, dtype=bool)
            for field, value in annotations.items():
                selected &= block[field] == state['labels'][field][value]
            if 'min_tokens' in bounds:
                selected &= block['tokens'] >= bounds['min_tokens']
            if 'max_tokens' in bounds:
                selected &= block['tokens'] <= bounds['max_tokens']
            mask[start:stop] = selected
    return mask


@lru_cache(maxsize=16)
def semantic_results(path, text, sources_json, annotations_json, bounds_json):
    with SEARCH_LOCK:
        faiss.omp_set_num_threads(4)
        state, index, metadata = snapshot(path)
        sources, annotations, bounds = set(json.loads(sources_json)), json.loads(annotations_json), json.loads(bounds_json)
        query = encode_documents(encoder(), [text])[0]
        if not np.any(query):
            return []
        allowed = eligibility(state, metadata, sources, annotations, bounds)
        if allowed is not None and not allowed.any():
            return []
        ann = vector_index(path)
        probes = min(64, ann.nlist)
        while True:
            _, identifiers = remote_ann.candidates(path, ann, query, probes, allowed)
            if len(identifiers) >= 100 or probes >= ann.nlist or allowed is None:
                break
            probes = min(probes * 4, ann.nlist)
        if not len(identifiers):
            return []
        vectors = remote_ann.original_vectors(path, state, identifiers)
        scores = vectors @ query
        return [{'record_no':int(identifiers[i]), 'score':float(scores[i])}
                for i in np.argsort(-scores, kind='stable')]


@lru_cache(maxsize=1024)
def ranked_record(path, identifier):
    _, index, _ = snapshot(path)
    searcher = index.searcher()
    result = searcher.search(tantivy.Query.term_query(index.schema, 'record_no', identifier), limit=1, count=False)
    if not result.hits:
        raise ValueError('Ranked record is missing from the complete index')
    return row_from_doc(searcher.doc(result.hits[0][1]))


def semantic_search(data, text, sources, annotations, bounds, offset=0, limit=30):
    rows = semantic_results(str(directory(data)), text, json.dumps(sorted(sources)),
                            json.dumps(annotations, sort_keys=True), json.dumps(bounds, sort_keys=True))
    page = [{**ranked_record(str(directory(data)), row['record_no']), 'score':row['score']}
            for row in rows[offset:offset + limit]]
    return {'rows': page, 'total': len(rows), 'has_more': offset + len(page) < len(rows),
            'next_offset': offset + len(page), 'approximate': True}


def original(data, source, row_index, identifier):
    state, index, _ = snapshot(str(directory(data)))
    entry = next((s for s in state['sources'] if s['id'] == source), None)
    if entry is None or not 0 <= row_index < entry['records']:
        raise ValueError('Unknown record location')
    query = tantivy.Query.term_query(index.schema, 'record_no', entry['offset'] + row_index)
    searcher = index.searcher(); result = searcher.search(query, limit=1, count=False)
    if not result.hits:
        raise ValueError('Record missing from the complete index')
    doc = searcher.doc(result.hits[0][1]).to_dict()
    if doc['id'][0].decode('utf-8') != identifier:
        raise ValueError('Record identity differs from the published release')
    return {'text': doc['text'][0], 'truncated': False}
