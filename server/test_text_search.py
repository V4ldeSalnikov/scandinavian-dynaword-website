import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tantivy
import duckdb
from server import app as app_module
from server import text_search as search


class TextSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.cache=Path(self.temp.name)
        self.patch=patch.object(search,'CACHE',self.cache);self.patch.start();search.get_index.cache_clear();search.metadata_clause.cache_clear()
        folder=self.cache/'fulltext';folder.mkdir()
        builder=tantivy.SchemaBuilder()
        builder.add_text_field('text',stored=True);builder.add_text_field('key',stored=True,tokenizer_name='raw')
        builder.add_unsigned_field('token_count',indexed=True,fast=True)
        for field in search.FIELDS:builder.add_text_field(field,tokenizer_name='raw')
        index=tantivy.Index(builder.build(),path=str(folder));writer=index.writer(heap_size=20_000_000,num_threads=1)
        for i,(text,source,quality,tokens) in enumerate([
            ('Danske vindmøller producerer vedvarende energi.','news','good',40),
            ('Vindmøller i Danmark og elektrisk energi.','books','poor',800),
            ('En bog om dansk litteratur og digte.','books','__missing__',100),
        ]):
            data={field:'__missing__' for field in search.FIELDS}
            data.update({'text':text,'key':f'{source}/{i}','source':source,'content_quality':quality,'educational_value':'high' if quality=='good' else 'none','token_count':tokens})
            writer.add_document(tantivy.Document.from_dict(data,index.schema))
        writer.commit();writer.wait_merging_threads();index.reload()

    def tearDown(self):
        search.get_index.cache_clear();search.metadata_clause.cache_clear();self.patch.stop();self.temp.cleanup()

    def test_full_text_and_metadata_filter(self):
        rows,count=search.search('vindmøller',{})
        self.assertEqual(count,2)
        rows,count=search.search('vindmøller',{'source':'news','content_quality':'good','max_tokens':100})
        self.assertEqual(count,1);self.assertEqual(rows[0]['source'],'news')

    def test_additional_indexed_fields_filter_before_counting(self):
        rows,count=search.search('vindmøller',{'educational_value':'none','content_quality':'poor'})
        self.assertEqual(count,1)
        self.assertEqual(rows[0]['source'],'books')

    def test_new_metadata_fields_intersect_before_pagination(self):
        (self.cache/'manifest.json').write_text(json.dumps({'status':'ready'}))
        with duckdb.connect(str(self.cache/'corpus.duckdb')) as connection:
            connection.execute('CREATE TABLE records (source VARCHAR,id VARCHAR,content_ratio VARCHAR,content_length VARCHAR)')
            connection.execute("INSERT INTO records VALUES ('news','0','complete_content','substantial'),('books','1','partial_content','minimal'),('books','2',NULL,NULL)")
        with patch.object(app_module,'CACHE',self.cache):
            rows,count=search.search('vindmøller',{'content_ratio':'partial_content','content_length':'minimal'},0,1)
            self.assertEqual(count,1)
            self.assertEqual(rows[0]['id'],'1')
            rows,count=search.search('vindmøller',{'content_length':'unknown'},0,1)
            self.assertEqual((rows,count),([],0))
            rows,count=search.search('vindmøller',{'content_length':'minimal','annotation_key':'content_length','annotation_value':'substantial'},0,1)
            self.assertEqual((rows,count),([],0))

    def test_reader_returns_complete_original(self):
        self.assertEqual(search.original_text('books','2'),'En bog om dansk litteratur og digte.')
        self.assertIsNone(search.original_text('books','missing'))

    def test_missing_and_pagination(self):
        rows,count=search.search('litteratur',{'content_quality':'__missing__'})
        self.assertEqual(count,1)
        a,count=search.search('vindmøller',{},0,1);b,_=search.search('vindmøller',{},1,1)
        self.assertEqual(count,2);self.assertNotEqual(a[0]['id'],b[0]['id'])


if __name__=='__main__':unittest.main()
