import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tantivy
from server import text_search as search


class TextSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.cache=Path(self.temp.name)
        self.patch=patch.object(search,'CACHE',self.cache);self.patch.start();search.get_index.cache_clear()
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
            data.update({'text':text,'key':f'{source}/{i}','source':source,'content_quality':quality,'token_count':tokens})
            writer.add_document(tantivy.Document.from_dict(data,index.schema))
        writer.commit();writer.wait_merging_threads();index.reload()

    def tearDown(self):
        search.get_index.cache_clear();self.patch.stop();self.temp.cleanup()

    def test_full_text_and_metadata_filter(self):
        rows,count=search.search('vindmøller',{})
        self.assertEqual(count,2)
        rows,count=search.search('vindmøller',{'source':'news','content_quality':'good','max_tokens':100})
        self.assertEqual(count,1);self.assertEqual(rows[0]['source'],'news')

    def test_reader_returns_complete_original(self):
        self.assertEqual(search.original_text('books','2'),'En bog om dansk litteratur og digte.')
        self.assertIsNone(search.original_text('books','missing'))

    def test_missing_and_pagination(self):
        rows,count=search.search('litteratur',{'content_quality':'__missing__'})
        self.assertEqual(count,1)
        a,count=search.search('vindmøller',{},0,1);b,_=search.search('vindmøller',{},1,1)
        self.assertEqual(count,2);self.assertNotEqual(a[0]['id'],b[0]['id'])


if __name__=='__main__':unittest.main()
