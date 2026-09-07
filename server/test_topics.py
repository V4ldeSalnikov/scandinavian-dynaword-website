import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import tantivy
from fastapi.testclient import TestClient

from server import app, semantic_search, text_search, topics


class TopicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name)
        self.patches = [patch.object(app, 'CACHE', self.cache), patch.object(text_search, 'CACHE', self.cache)]
        for p in self.patches:
            p.start()
        for cache in [app.stats_cached, topics.view_cached, topics._topic_term_query, text_search.get_index, semantic_search.search_cached]:
            cache.cache_clear()
        (self.cache/'manifest.json').write_text(json.dumps({'status': 'ready', 'revision': 'test', 'sources': []}))
        (self.cache/'semantic_manifest.json').write_text(json.dumps({'metadata_fingerprint': 'test-ids'}))
        (self.cache/'search_manifest.json').write_text(json.dumps({'status': 'ready', 'revision': 'test'}))
        state = {'status': 'ready', 'revision': 'test', 'metadata_fingerprint': 'test-ids', 'topics': [{'id': 0}, {'id': 1}]}
        (self.cache/'topics_manifest.json').write_text(json.dumps(state))
        (self.cache/'topics').mkdir()
        pq.write_table(pa.table({'record_no': [0, 1, 2, 3], 'topic_id': [0, 1, -1, 0], 'topic_similarity': [.9, .8, 0, .7]}), self.cache/'topics/assignments.parquet')
        # Only one of the two topic-0 records appears on the map.
        pq.write_table(pa.table({'record_no': [0, 1], 'x': [1., 2.], 'y': [2., 3.], 'preview': ['wind power', 'other energy']}), self.cache/'topics/points.parquet')
        with duckdb.connect(str(self.cache/'corpus.duckdb')) as c:
            c.execute('''CREATE TABLE records (record_no BIGINT,id VARCHAR,source VARCHAR,domain VARCHAR,token_count BIGINT,added VARCHAR,created VARCHAR,source_row BIGINT,one_sentence_description VARCHAR,content_quality VARCHAR,pii_presence VARCHAR,content_type VARCHAR[])''')
            c.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [
                (i, str(i), 'news', 'News', 10*(i+1), '', '', i, '', 'good' if i != 3 else 'poor', 'no_pii', ['news_report']) for i in range(4)
            ])
        folder = self.cache/'fulltext'
        folder.mkdir()
        builder = tantivy.SchemaBuilder()
        builder.add_text_field('text', stored=True)
        builder.add_text_field('key', stored=True, tokenizer_name='raw')
        builder.add_unsigned_field('token_count', indexed=True, fast=True)
        for field in text_search.FIELDS:
            builder.add_text_field(field, tokenizer_name='raw')
        index = tantivy.Index(builder.build(), path=str(folder))
        writer = index.writer(heap_size=20_000_000, num_threads=1)
        for i in range(4):
            fields = {field: '__missing__' for field in text_search.FIELDS}
            fields.update(text='Vindmøller og energi ' * (i+1), key=f'news/{i}', source='news', domain='News', content_quality='poor' if i == 3 else 'good', token_count=10*(i+1))
            writer.add_document(tantivy.Document.from_dict(fields, index.schema))
        writer.commit()
        writer.wait_merging_threads()
        self.client = TestClient(app.app)

    def tearDown(self):
        for cache in [app.stats_cached, topics.view_cached, topics._topic_term_query, text_search.get_index, semantic_search.search_cached]:
            cache.cache_clear()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_topic_counts_rows_and_sample_have_distinct_scopes(self):
        params = {'filters': json.dumps({'topic_id': 0})}
        view = self.client.get('/api/topics/view', params=params).json()
        stats = self.client.get('/api/stats', params=params).json()
        rows = self.client.get('/api/rows', params=params).json()['rows']
        self.assertEqual(view['base_records'], 4)
        self.assertEqual(view['selected_records'], 2)
        self.assertEqual(stats['totals']['records'], 2)
        self.assertEqual([r['record_no'] for r in rows], [0, 3])
        self.assertEqual([p[0] for p in view['points']], [0])
        counts = {d['topic_id']: d['records'] for d in view['distributions']}
        self.assertEqual(counts, {0: 2, 1: 1, -1: 1})
        filtered = self.client.get('/api/topics/view', params={'filters': json.dumps({'topic_id': 0, 'content_quality': 'poor'})}).json()
        self.assertEqual(filtered['selected_records'], 1)
        self.assertEqual(filtered['points'], [])  # Empty map != empty full corpus.

    def test_text_topic_filter_is_applied_before_counting_and_pagination(self):
        first, count = text_search.search('vindmøller', {'topic_id': 0}, limit=1)
        second, count2 = text_search.search('vindmøller', {'topic_id': 0}, offset=1, limit=1)
        self.assertEqual(count, 2)
        self.assertEqual(count2, 2)
        self.assertEqual({first[0]['id'], second[0]['id']}, {'0', '3'})
        filtered, count = text_search.search('vindmøller', {'topic_id': 0, 'content_quality': 'poor'})
        self.assertEqual(count, 1)
        self.assertEqual(filtered[0]['id'], '3')
        missing, count = text_search.search('vindmøller', {'topic_id': -1})
        self.assertEqual(count, 1)
        self.assertEqual(missing[0]['id'], '2')

    def test_semantic_filter_uses_all_topic_records_including_unmapped_ones(self):
        class Encoder:
            def encode(self, text): return np.array([1., 0.])
            def query_words(self, text): return np.array([[1., 0.]]), np.ones(1)
            def concept_coverage(self, *args): return .5
        vectors = np.array([[.8,.2],[1.,0.],[0.,0.],[.9,.1]], dtype=np.float16)
        with patch.object(semantic_search, 'encoder', return_value=Encoder()), patch.object(semantic_search, 'status', return_value={'records_processed': 4}), patch.object(semantic_search, 'source_vectors', return_value=(vectors, np.arange(4))):
            ranked, compared = semantic_search.search_cached('energi', '{"topic_id":0}')
        self.assertEqual(compared, 2)
        self.assertEqual([r['record_no'] for r in ranked], [3,0])

    def test_invalid_topics_and_stale_sidecars_are_rejected(self):
        for value in [999, '0 OR TRUE', [], True, 0.5]:
            response = self.client.get('/api/rows', params={'filters': json.dumps({'topic_id': value})})
            self.assertEqual(response.status_code, 400)
        (self.cache/'semantic_manifest.json').write_text(json.dumps({'metadata_fingerprint': 'different-identities'}))
        self.assertEqual(self.client.get('/api/topics').json()['status'], 'stale')
        self.assertEqual(self.client.get('/api/rows', params={'filters': '{"topic_id":0}'}).status_code, 503)


if __name__ == '__main__':
    unittest.main()
