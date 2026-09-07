import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
from fastapi.testclient import TestClient
from server import app as module


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name)
        self.patch = patch.object(module, 'CACHE', self.cache)
        self.patch.start()
        module.stats_cached.cache_clear()
        (self.cache/'manifest.json').write_text(json.dumps({'status':'ready','revision':'test','sources':[]}))
        c=duckdb.connect(str(self.cache/'corpus.duckdb'))
        c.execute('''CREATE TABLE records (record_no BIGINT,id VARCHAR,source VARCHAR,domain VARCHAR,token_count BIGINT,added VARCHAR,created VARCHAR,source_row BIGINT,one_sentence_description VARCHAR,content_quality VARCHAR,pii_presence VARCHAR,content_type VARCHAR[],original_source VARCHAR)''')
        c.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',[
            (0,'a','news','News',10,'2025-01-01','2020-01-01, 2020-12-31',0,'alpha','good','contains_pii',['news_report','opinion'],'news'),
            (1,'b','news','News',50,'2025-01-01','2020-01-01, 2020-12-31',1,'beta','poor','no_pii',['news_report'],'news'),
            (2,'c','books','Books',1000,'2025-01-01','1900-01-01, 1900-12-31',0,None,None,None,None,'books'),
            (3,'d','books','Books',100,'2025-01-01','1900-01-01, 1900-12-31',1,'delta','good','no_pii',['creative','creative'],'books'),
        ])
        c.close()
        self.client=TestClient(module.app)

    def tearDown(self):
        module.stats_cached.cache_clear()
        self.patch.stop()
        self.temp.cleanup()

    def test_complete_stats_and_histogram_totals(self):
        r=self.client.get('/api/stats').json()
        self.assertEqual(r['totals'],{'records':4,'tokens':1160,'sources':2,'annotated':3})
        self.assertEqual(sum(b['records'] for b in r['histogram']),4)
        self.assertEqual(sum(b['records'] for b in r['annotations']),4)
        self.assertEqual(r['annotation_covered'],3)

    def test_combined_filters_and_rows_agree(self):
        params={'filters':json.dumps({'source':'news','pii_presence':'contains_pii','min_tokens':5,'max_tokens':30})}
        stats=self.client.get('/api/stats',params=params).json()
        rows=self.client.get('/api/rows',params=params).json()
        self.assertEqual(stats['totals']['records'],1)
        self.assertEqual(stats['totals']['tokens'],10)
        self.assertEqual([r['id'] for r in rows['rows']],['a'])

    def test_missing_is_not_negative(self):
        missing=self.client.get('/api/rows',params={'filters':json.dumps({'pii_presence':'__missing__'})}).json()
        negative=self.client.get('/api/rows',params={'filters':json.dumps({'pii_presence':'no_pii'})}).json()
        self.assertEqual([r['id'] for r in missing['rows']],['c'])
        self.assertEqual([r['id'] for r in negative['rows']],['b','d'])

    def test_multilabel_does_not_duplicate_record_counts(self):
        r=self.client.get('/api/stats',params={'annotation':'content_type'}).json()
        counts={d['name']:d['records'] for d in r['annotations']}
        self.assertEqual(counts,{'news_report':2,'opinion':1,'creative':1,'__missing__':1})
        self.assertEqual(r['annotation_covered'],3)
        rows=self.client.get('/api/rows',params={'filters':json.dumps({'annotation_key':'content_type','annotation_value':'creative'})}).json()
        self.assertEqual(len(rows['rows']),1)

    def test_pagination_and_empty_selection(self):
        p1=self.client.get('/api/rows',params={'limit':2}).json()
        p2=self.client.get('/api/rows',params={'offset':p1['next_offset'],'limit':2}).json()
        self.assertTrue(p1['has_more']);self.assertFalse(p2['has_more'])
        self.assertEqual([r['id'] for r in p1['rows']+p2['rows']],['a','b','c','d'])
        empty=self.client.get('/api/stats',params={'filters':'{"min_tokens":10000}'}).json()
        self.assertEqual(empty['totals']['records'],0)
        self.assertEqual(empty['totals']['tokens'],0)

    def test_untrusted_filters_are_parameters(self):
        result=self.client.get('/api/rows',params={'filters':json.dumps({'source':"'; DROP TABLE records; --"})})
        self.assertEqual(result.status_code,200);self.assertEqual(result.json()['rows'],[])
        self.assertEqual(self.client.get('/api/stats').json()['totals']['records'],4)
        self.assertEqual(self.client.get('/api/stats',params={'annotation':'id);DROP TABLE records;--'}).status_code,400)

    def test_unicode_reader_pagination_does_not_skip_characters(self):
        text = 'Dansk 🌍 tekst med æøå og endnu mere.'
        with patch.object(module, 'load_text', return_value={'text': text, 'truncated': False}):
            first = self.client.get('/api/record/0', params={'limit': 9}).json()
            rest = self.client.get('/api/record/0', params={'offset': first['next_offset']}).json()
        self.assertEqual(first['text'] + rest['text'], text)
        self.assertTrue(first['has_more'])
        self.assertFalse(rest['has_more'])


if __name__=='__main__':
    unittest.main()
