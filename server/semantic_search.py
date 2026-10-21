"""Full-corpus vector retrieval with filtered ANN and exact-search fallback."""
from functools import lru_cache
from pathlib import Path
import json
import threading

import numpy as np
from server.embeddings import CACHE, encoder
from server import ann_search

SEARCH_LOCK = threading.Lock()
MAX_RESULTS = 300
CANDIDATES = 1200
RETRIEVAL = {'candidates': CANDIDATES, 'results': MAX_RESULTS, 'method': 'Exact document cosine candidates, reranked with 45% document cosine and 55% weighted query-concept coverage using Danish word-vector similarities.'}


def status():
    path = CACHE/'semantic_manifest.json'
    result = json.loads(path.read_text()) if path.exists() else {'status': 'building', 'records_processed': 0, 'records_with_vectors': 0}
    ann = ann_search.status(result)
    retrieval = RETRIEVAL if ann['status'] != 'ready' else {
        **RETRIEVAL, 'approximate': True, 'indexed_records': ann['records'], 'nprobe': ann_search.NPROBE, 'ann_candidates': 2400,
        'method': 'Faiss IVF-SQ8 approximate retrieval over the full vector corpus, filtered before selection; original-vector cosine and query-concept reranking.'}
    return {**result, 'retrieval': retrieval, 'ann_index': ann}


@lru_cache(maxsize=50)
def source_vectors(source):
    folder = CACHE/'semantic'
    return np.load(folder/f'{source}.npy', mmap_mode='r'), np.load(folder/f'{source}.ids.npy', mmap_mode='r')


def rank(query_vector, sources, eligible=None, limit=MAX_RESULTS):
    best_ids, best_scores = np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float32)
    compared = 0
    for source in sources:
        vectors, identifiers = source_vectors(source)
        for start in range(0, len(identifiers), 32768):
            ids = identifiers[start:start+32768]
            mask = eligible[ids] if eligible is not None else np.ones(len(ids), dtype=bool)
            if not np.any(mask):
                continue
            v = np.asarray(vectors[start:start+32768][mask], dtype=np.float32)
            ids = ids[mask]
            norms = np.linalg.norm(v, axis=1)
            valid = norms > 0
            compared += int(np.count_nonzero(valid))
            scores = np.einsum('ij,j->i', v, query_vector) / np.maximum(norms, 1e-12)
            ids, scores = ids[valid], scores[valid]
            if len(scores) > limit:
                top = np.argpartition(scores, -limit)[-limit:]
                ids, scores = ids[top], scores[top]
            best_ids = np.concatenate([best_ids, ids])
            best_scores = np.concatenate([best_scores, scores])
            if len(best_scores) > limit:
                top = np.argpartition(best_scores, -limit)[-limit:]
                best_ids, best_scores = best_ids[top], best_scores[top]
    order = np.lexsort((best_ids, -best_scores))
    return [{'record_no': int(best_ids[i]), 'score': float(best_scores[i])} for i in order], compared


@lru_cache(maxsize=12)
def search_cached(text, filters_json):
    # Import here to avoid a circular dependency with the API's validated filters.
    from server.app import database, parse_filters
    query = encoder().encode(text)
    if not np.any(query):
        raise ValueError('No words in this query are in the Danish vector vocabulary. Try other Danish words or use text search.')
    where, params = parse_filters(filters_json)
    state = status()
    with SEARCH_LOCK, database() as c:
        sources = [r[0] for r in c.execute(f'SELECT DISTINCT source FROM records WHERE {where}', params).fetchall()]
        eligible = None
        if where != 'TRUE':
            eligible = np.zeros(state['records_processed'], dtype=bool)
            ids = c.execute(f'SELECT record_no FROM records WHERE {where}', params).fetchnumpy()['record_no']
            eligible[ids] = True
        if state.get('ann_index', {}).get('status') == 'ready' and (eligible is None or np.count_nonzero(eligible) > 100_000):
            candidates, compared = ann_search.rank(query, sources, eligible, limit=CANDIDATES)
        else:
            candidates, compared = rank(query, sources, eligible, limit=CANDIDATES)
        if not candidates:
            return [], compared
        from server.text_search import original_texts
        metadata = c.execute('SELECT record_no,source,id FROM records WHERE record_no IN (SELECT unnest(?))', [[r['record_no'] for r in candidates]]).fetchall()
        identities = {number: (source, identifier) for number, source, identifier in metadata}
        model = encoder()
        query_vectors, query_weights = model.query_words(text)
        texts = original_texts(identities[r['record_no']] for r in candidates)
        for candidate, raw in zip(candidates, texts):
            coverage = model.concept_coverage(raw or '', query_vectors, query_weights)
            candidate['score'] = .45*candidate['score'] + .55*coverage
        candidates.sort(key=lambda r: (-r['score'], r['record_no']))
        return candidates[:MAX_RESULTS], compared
