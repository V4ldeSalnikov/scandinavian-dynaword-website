"""Validate the prepared snapshot and both search indexes, without network calls."""
from pathlib import Path
import hashlib
import json
import sys

import duckdb
import numpy as np
import tantivy

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'.cache'


def main():
    manifest = json.loads((CACHE/'manifest.json').read_text())
    text = json.loads((CACHE/'search_manifest.json').read_text())
    semantic = json.loads((CACHE/'semantic_manifest.json').read_text())
    assert manifest['status'] == text['status'] == semantic['status'] == 'ready'
    assert manifest['revision'] == text['revision'] == semantic['revision']
    sources = {s['id'] for s in manifest['sources']}
    assert sources == set(text['sources']) == set(semantic['sources'])
    with duckdb.connect(str(CACHE/'corpus.duckdb'), read_only=True) as c:
        records, tokens, annotated = c.execute('SELECT count(*),sum(token_count),count(content_quality) FROM records').fetchone()
        assert records == manifest['records'] == text['records'] == semantic['records_processed']
        assert records == manifest['published_stats']['number_of_samples']
        assert tokens == manifest['tokens']
        assert annotated == manifest['annotated'] == manifest['published_stats']['annotations']['number_of_annotated_documents']
        assert c.execute('SELECT count(*) FROM (SELECT source,id FROM records GROUP BY source,id HAVING count(*)>1)').fetchone()[0] == 0
        for field, expected in manifest['published_stats']['annotations']['property_level_counts'].items():
            # Field names come from the pinned local manifest, not request input.
            actual = dict(c.execute(f'SELECT "{field}",count(*) FROM records WHERE "{field}" IS NOT NULL GROUP BY "{field}"').fetchall())
            assert actual == expected, f'Annotation distribution differs: {field}'
        seen = np.zeros(records, dtype=bool)
        usable = 0
        for source in manifest['sources']:
            name = source['id']
            ids = np.load(CACHE/'semantic'/f'{name}.ids.npy', mmap_mode='r')
            vectors = np.load(CACHE/'semantic'/f'{name}.npy', mmap_mode='r')
            assert vectors.shape == (source['records'], 300)
            assert len(np.unique(ids)) == source['records']
            assert not np.any(seen[ids])
            seen[ids] = True
            expected_ids = c.execute('SELECT record_no FROM records WHERE source=?', [name]).fetchnumpy()['record_no']
            assert np.array_equal(np.sort(ids), np.sort(expected_ids)), f'Vector/source identity mismatch: {name}'
            for start in range(0, len(ids), 32768):
                chunk = vectors[start:start+32768]
                assert np.isfinite(chunk).all()
                usable += int(np.count_nonzero(np.any(chunk, axis=1)))
        assert seen.all()
        assert usable == semantic['records_with_vectors']
    index = tantivy.Index.open(str(CACHE/'fulltext'))
    assert index.searcher().num_docs == records
    with (CACHE/'corpus.duckdb').open('rb') as corpus_file:
        assert semantic['metadata_fingerprint'] == hashlib.file_digest(corpus_file, 'sha256').hexdigest()
    print(f'PASS: {records:,} unique records; {len(sources)} sources; both indexes cover the complete snapshot.')
    print(f'PASS: {annotated:,} annotated records; all published annotation distributions match.')
    print(f'PASS: {usable:,} usable semantic vectors; {records-usable:,} records without recognized vocabulary.')
    print(f'Tokens: {tokens:,}; published-summary difference: {tokens-manifest["published_stats"]["number_of_tokens"]:+,}. See README audit.')


if __name__ == '__main__':
    main()
