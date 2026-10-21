"""Build a compact IVF-SQ8 candidate index over every existing Danish vector.

The original vectors remain the source for exact candidate reranking. No texts,
embeddings, record identities, or metadata are changed by this build.
"""
import hashlib
import json
from pathlib import Path
import time

import faiss
import numpy as np

CACHE = Path(__file__).resolve().parents[1] / '.cache'


def build():
    state = json.loads((CACHE / 'semantic_manifest.json').read_text())
    assert state['status'] == 'ready'
    destination = CACHE / 'semantic-ann'
    destination.mkdir(exist_ok=True)
    faiss.omp_set_num_threads(4)
    rng = np.random.default_rng(42)
    # Uniform sampling across the vector-bearing corpus, rather than per-source
    # quotas, keeps the candidate index representative of the retrieval space.
    chunks = []
    for source in state['sources']:
        v = np.load(CACHE / 'semantic' / f'{source}.npy', mmap_mode='r')
        count = min(len(v), max(1, round(160_000 * len(v) / state['records_processed'])))
        x = np.array(v[rng.choice(len(v), count, replace=False)], dtype=np.float32)
        x = x[np.any(x, axis=1)]
        chunks.append(x)
    training = np.ascontiguousarray(np.concatenate(chunks))
    faiss.normalize_L2(training)
    index = faiss.IndexIVFScalarQuantizer(faiss.IndexFlatIP(300), 300, 1024, faiss.ScalarQuantizer.QT_8bit, faiss.METRIC_INNER_PRODUCT)
    index.cp.seed = 42
    index.cp.niter = 20
    started = time.monotonic()
    print(f'Training IVF-SQ8 on {len(training):,} vectors', flush=True)
    index.train(training)
    print(f'Trained in {time.monotonic()-started:.1f}s', flush=True)
    for source in state['sources']:
        matrix = np.load(CACHE / 'semantic' / f'{source}.npy', mmap_mode='r')
        ids = np.load(CACHE / 'semantic' / f'{source}.ids.npy', mmap_mode='r')
        for start in range(0, len(ids), 32768):
            x = np.array(matrix[start:start+32768], dtype=np.float32)
            valid = np.any(x, axis=1)
            x = np.ascontiguousarray(x[valid])
            faiss.normalize_L2(x)
            index.add_with_ids(x, np.ascontiguousarray(ids[start:start+32768][valid], dtype=np.int64))
        print(f'{source}: {index.ntotal:,} indexed', flush=True)
    assert index.ntotal == state['records_with_vectors']
    index.nprobe = 64
    partial = destination / 'index.partial.faiss'
    faiss.write_index(index, str(partial))
    partial.replace(destination / 'index.faiss')
    with (destination / 'index.faiss').open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'status': 'ready', 'revision': state['revision'],
              'metadata_fingerprint': state['metadata_fingerprint'],
              'matrix_sha256': state['model']['matrix_sha256'],
              'records': index.ntotal, 'dimensions': 300,
              'method': 'Faiss IVF1024,SQ8 with cosine candidates; original-vector cosine reranking',
              'nprobe': 64, 'candidates': 2400, 'seed': 42,
              'faiss_version': faiss.__version__, 'sha256': checksum}
    (destination / 'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f'Ready: {(destination / "index.faiss").stat().st_size/1e6:.1f} MB, {time.monotonic()-started:.1f}s', flush=True)


if __name__ == '__main__':
    build()
