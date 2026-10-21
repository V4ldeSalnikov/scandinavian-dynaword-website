"""Full-coverage IVF-SQ8 retrieval with filtering before candidate selection."""
from functools import lru_cache
import json
import os
from pathlib import Path

import faiss
import numpy as np

ROOT = Path(__file__).resolve().parents[1] / '.cache'
NPROBE = 512  # Search more partitions than the build default to preserve recall.
THREADS = max(1, min(4, int(os.environ.get('DYNAWORD_SEARCH_THREADS', '2'))))


def status(semantic):
    path = ROOT / 'semantic-ann' / 'manifest.json'
    if not path.exists() or not (path.parent / 'index.faiss').exists():
        return {'status': 'unavailable'}
    state = json.loads(path.read_text())
    if (state.get('status') != 'ready' or state.get('revision') != semantic.get('revision')
            or state.get('metadata_fingerprint') != semantic.get('metadata_fingerprint')
            or state.get('matrix_sha256') != semantic.get('model', {}).get('matrix_sha256')
            or state.get('records') != semantic.get('records_with_vectors')):
        return {'status': 'stale'}
    return state


@lru_cache(maxsize=1)
def index_for(path):
    faiss.omp_set_num_threads(THREADS)
    index = faiss.read_index(path)
    if index.d != 300:
        raise ValueError('Unexpected ANN vector dimension')
    return index


def candidates(query, eligible=None, limit=2400):
    faiss.omp_set_num_threads(THREADS)
    index = index_for(str(ROOT / 'semantic-ann' / 'index.faiss'))
    # A bitmap is bounded at under 1 MB for the entire corpus. Its lifetime
    # extends through search because Faiss keeps the selector's buffer pointer.
    bitmap = selector = None
    if eligible is not None:
        bitmap = np.packbits(eligible, bitorder='little')
        selector = faiss.IDSelectorBitmap(len(bitmap), faiss.swig_ptr(bitmap))
    params = faiss.SearchParametersIVF(nprobe=NPROBE)
    if selector is not None:
        params.sel = selector
    scores, identifiers = index.search(np.ascontiguousarray(query[None, :], dtype=np.float32), limit, params=params)
    return identifiers[0][identifiers[0] >= 0]


@lru_cache(maxsize=50)
def source_lookup(source):
    from server.semantic_search import source_vectors
    _, identifiers = source_vectors(source)
    # Parallel preparation preserved record identity, but not row order.
    order = np.argsort(identifiers)
    return identifiers[order], order


def rank(query, sources, eligible=None, limit=1200):
    from server.semantic_search import source_vectors
    ids = candidates(query, eligible, max(2400, limit*2))
    if not len(ids):
        return [], 0
    # Remove quantization error from returned scores using the original vectors.
    result = []
    for source in sources:
        vectors, _ = source_vectors(source)
        identifiers, order = source_lookup(source)
        positions = np.searchsorted(identifiers, ids)
        valid = positions < len(identifiers)
        positions, selected = positions[valid], ids[valid]
        matches = identifiers[positions] == selected
        positions, selected = positions[matches], selected[matches]
        if not len(selected):
            continue
        matrix = np.asarray(vectors[order[positions]], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1)
        scores = matrix @ query / np.maximum(norms, 1e-12)
        result.extend({'record_no': int(i), 'score': float(s)} for i, s in zip(selected, scores))
    result.sort(key=lambda x: (-x['score'], x['record_no']))
    return result[:limit], len(ids)
