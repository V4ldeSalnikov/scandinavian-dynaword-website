import unittest
import numpy as np
from server import annotation_index as index
from server.remote_corpora import filters_for, quote, range_groups
from fastapi import HTTPException


class AnnotationIndexTests(unittest.TestCase):
    def setUp(self):
        self.rows=np.array([(index.identity_hash('a'),10,1,1),(index.identity_hash('b'),20,2,1),(index.identity_hash('c'),30,2,2),(index.identity_hash('d'),40,0,2)],dtype=[('id_hash','u8'),('tokens','u4'),('content_quality','u1'),('pii_presence','u1')])
        self.entry={'sources':[{'id':'first','offset':0,'records':2},{'id':'second','offset':2,'records':2}], 'labels':{'content_quality':{'good':1,'excellent':2},'pii_presence':{'no_pii':1,'contains_pii':2}}}
        self.index=(self.entry,self.rows)

    def test_intersections_count_all_records_before_pagination(self):
        self.assertEqual(index.select(self.index,{'first','second'},{'content_quality':'excellent'},{'min_tokens':15},1,1),([2],2))
        self.assertEqual(index.select(self.index,{'first','second'},{'content_quality':'excellent','pii_presence':'contains_pii'},{},0,30),([2],1))
        self.assertEqual(index.select(self.index,{'first'},{'content_quality':'excellent'},{},0,30),([1],1))

    def test_source_boundaries_and_record_identity(self):
        self.assertEqual(index.location(self.index,2),('second',0))
        self.assertEqual(index.annotations_at(self.index,2,'c')['content_quality'],'excellent')
        self.assertIsNone(index.annotations_at(self.index,3,'d')['content_quality'])
        with self.assertRaises(ValueError):index.annotations_at(self.index,2,'other')

    def test_filter_fields_and_values_are_allowlisted(self):
        data={'sources':[{'id':'first','domain':'Legal'}],'annotation_distributions':{'content_quality':{'good':1}}}
        for raw in ['[]','{"annotations":{"unknown":"x"}}','{"annotations":{"content_quality":"bad"}}','{"min_tokens":-1}','{"source":"missing"}']:
            with self.assertRaises(HTTPException):filters_for(data,raw)
        self.assertEqual(quote("O'Brien"),"'O''Brien'")
        self.assertEqual(range_groups([5,2,1,2,9]),[[1,2],[5],[9]])

if __name__=='__main__':unittest.main()
