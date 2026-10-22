import json
import unittest
from unittest.mock import patch
import numpy as np
from fastapi import HTTPException
from server import corpus_stats as stats, remote_corpora as remote


class CorpusStatsTests(unittest.TestCase):
    def setUp(self):
        self.data = {'id':'faroese', 'revision':'abc', 'sources':[
            {'id':'a','domain':'Books','records':3,'tokens':65,'annotated':2,'annotation_distributions':{'content_quality':{'good':1,'poor':1}}},
            {'id':'b','domain':'News','records':2,'tokens':128,'annotated':2,'annotation_distributions':{'content_quality':{'good':2}}}],
            'annotation_distributions':{'content_quality':{'good':3,'poor':1},'pii_presence':{'no_pii':4}}}
        self.index = ({'sources':[{'id':'a','offset':0,'records':3},{'id':'b','offset':3,'records':2}],
                       'labels':{'content_quality':{'good':1,'poor':2},'pii_presence':{'no_pii':1,'contains_pii':2}}},
                      np.array([(0,1,1),(16,2,2),(49,0,1),(64,1,1),(64,1,1)],dtype=[('tokens','u4'),('content_quality','u1'),('pii_presence','u1')]))
        stats.cached.cache_clear()

    def run_stats(self, sources=None, annotations=None, bounds=None):
        return stats.aggregate(self.data, sources if sources is not None else self.data['sources'], annotations or {}, bounds or {}, 'content_quality', self.index)

    def test_complete_counts_histogram_and_missing_labels(self):
        result=self.run_stats()
        self.assertEqual(result['totals'],{'records':5,'tokens':193,'sources':2,'annotated':4})
        self.assertEqual(sum(x['records'] for x in result['histogram']),5)
        self.assertEqual(result['histogram'][0]['records'],1)
        self.assertEqual(result['histogram'][1]['records'],1)
        self.assertEqual(result['annotation_covered'],4)
        self.assertEqual({a['name']:a['records'] for a in result['annotations']},{'__missing__':1,'good':3,'poor':1})

    def test_intersections_and_inclusive_bounds(self):
        result=self.run_stats(annotations={'content_quality':'good','pii_presence':'no_pii'},bounds={'min_tokens':64,'max_tokens':64})
        self.assertEqual(result['totals'],{'records':2,'tokens':128,'sources':1,'annotated':2})
        self.assertEqual(result['domains'],[{'name':'News','records':2,'tokens':128}])
        self.assertEqual(self.run_stats(bounds={'min_tokens':65})['totals']['records'],0)
        self.assertEqual(self.run_stats(sources=[])['totals']['sources'],0)
        self.assertEqual(self.run_stats(annotations={'content_quality':'__missing__'})['totals']['records'],1)

    def test_published_fallback_never_misrepresents_unavailable_annotations_or_filters(self):
        data={**self.data,'annotation_distributions':None}
        result=stats.aggregate(data,[data['sources'][1]],{}, {},'content_quality')
        self.assertEqual(result['totals']['records'],2)
        self.assertFalse(result['annotations_available'])
        self.assertFalse(result['histogram_available'])
        with self.assertRaises(ValueError):
            stats.aggregate(data,data['sources'],{}, {'min_tokens':20},'content_quality')

    def test_api_validates_filters_and_aggregates_complete_metadata(self):
        with patch.object(remote,'corpus',return_value=self.data), patch.object(stats.annotation_index,'load',return_value=self.index), patch.object(stats.corpus_search,'status',return_value={'text':False}):
            result=remote.stats('faroese',json.dumps({'source':'a','annotations':{'content_quality':'__missing__'}}))
            self.assertEqual(result['totals']['tokens'],49)
            for filters in [{'annotations':{'content_quality':'invented'}},{'source':'missing'},{'min_tokens':-1}]:
                with self.assertRaises(HTTPException): remote.stats('faroese',json.dumps(filters))
            with self.assertRaises(HTTPException): remote.stats('faroese',annotation='invented')

if __name__ == '__main__':unittest.main()
