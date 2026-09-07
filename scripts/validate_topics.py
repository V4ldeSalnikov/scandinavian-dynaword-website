"""Independent full-corpus coverage and sampled assignment audit for topic outputs."""
from pathlib import Path
import hashlib
import json

import duckdb
import numpy as np
import pyarrow.parquet as pq

CACHE = Path(__file__).resolve().parents[1]/'.cache'


def main():
    state = json.loads((CACHE/'topics_manifest.json').read_text())
    manifest = json.loads((CACHE/'manifest.json').read_text())
    semantic = json.loads((CACHE/'semantic_manifest.json').read_text())
    assert state['status'] == 'ready'
    assert state['revision'] == manifest['revision'] == semantic['revision']
    with (CACHE/'corpus.duckdb').open('rb') as file:
        assert state['metadata_fingerprint'] == hashlib.file_digest(file, 'sha256').hexdigest()
    with duckdb.connect(str(CACHE/'corpus.duckdb'), read_only=True) as c:
        assignments = pq.read_table(CACHE/'topics/assignments.parquet')
        c.register('assignments', assignments)
        c.register('points', pq.read_table(CACHE/'topics/points.parquet'))
        assert c.execute('SELECT count(*), count(DISTINCT record_no) FROM assignments').fetchone() == (manifest['records'], manifest['records'])
        assert c.execute('SELECT count(*) FROM records ANTI JOIN assignments USING(record_no)').fetchone()[0] == 0
        assert c.execute('SELECT count(*) FROM assignments ANTI JOIN records USING(record_no)').fetchone()[0] == 0
        counts = dict(c.execute('SELECT topic_id,count(*) FROM assignments GROUP BY topic_id').fetchall())
        assert counts.pop(-1) == state['unassigned'] == manifest['records']-semantic['records_with_vectors']
        assert counts == {t['id']: t['records'] for t in state['topics']}
        assert sum(counts.values()) == state['assigned']
        assert c.execute('SELECT count(*), count(DISTINCT record_no) FROM points').fetchone() == (state['sample_records'], state['sample_records'])
        assert dict(c.execute('SELECT source,count(*) FROM records JOIN points USING(record_no) GROUP BY source').fetchall()) == state['sample_sources']
        assert set(state['sample_sources']) == {s['id'] for s in manifest['sources']}
        assert c.execute('SELECT count(*) FROM points JOIN assignments USING(record_no) WHERE topic_id=-1 OR NOT isfinite(x) OR NOT isfinite(y)').fetchone()[0] == 0
        assert c.execute('SELECT count(*) FROM assignments WHERE NOT isfinite(topic_similarity) OR topic_similarity < -1.001 OR topic_similarity > 1.001').fetchone()[0] == 0
        # Check independent random rows from every source against saved centroids.
        centroids = np.load(CACHE/'topics/centroids.npy')
        class_ids = np.array(sorted(counts))
        indexed = np.empty(manifest['records'], dtype=np.int16)
        indexed[assignments['record_no'].to_numpy()] = assignments['topic_id'].to_numpy()
        rng = np.random.default_rng(173)
        checked = 0
        for source in manifest['sources']:
            ids = np.load(CACHE/'semantic'/f"{source['id']}.ids.npy", mmap_mode='r')
            matrix = np.load(CACHE/'semantic'/f"{source['id']}.npy", mmap_mode='r')
            positions = rng.choice(len(ids), size=min(100, len(ids)), replace=False)
            v = np.asarray(matrix[positions], dtype=np.float32)
            predicted = class_ids[np.argmax(v @ centroids.T, axis=1)]
            predicted[~np.any(v, axis=1)] = -1
            assert np.array_equal(predicted, indexed[ids[positions]])
            checked += len(positions)
    print(f"PASS: all {manifest['records']:,} records accounted for; {len(counts)} topics; {state['unassigned']:,} unassigned.")
    print(f"PASS: {state['sample_records']:,} unique map points across all 50 sources; topic counts and metadata joins agree.")
    print(f'PASS: {checked:,} independent centroid-assignment checks across every source.')


if __name__ == '__main__':
    main()
