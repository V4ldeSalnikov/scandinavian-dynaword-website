import json
import unittest
from unittest.mock import patch, Mock
from fastapi import HTTPException
from server import remote_corpora as remote

DATA={'id':'faroese','repo':'org/test','revision':'abc','records':3,'sources':[{'id':'a','domain':'Legal','records':2},{'id':'b','domain':'News','records':1}],'annotation_distributions':{'content_quality':{'good':1}}}


class RemoteCorporaTests(unittest.TestCase):
    def tearDown(self):remote.hub_cached.cache_clear()

    def test_changed_revision_and_partial_results_rejected(self):
        for revision,body,code in [('other',{'rows':[]},409),('abc',{'partial':True},503)]:
            response=Mock(status_code=200,ok=True,headers={'x-revision':revision})
            response.json.return_value=body
            with patch.object(remote,'corpus',return_value=DATA),patch.object(remote.requests,'get',return_value=response):
                with self.assertRaises(HTTPException) as error:remote.hub('faroese','rows',config='default')
                self.assertEqual(error.exception.status_code,code)

    def test_annotations_never_attach_to_mismatched_record_or_source(self):
        entry={'row_idx':0,'row':{'id':'text-id','source':'a','text':'original','token_count':2}}
        for candidate in [{'id':'other','dataset':'a','content_quality':'good'}, {'id':'text-id','dataset':'b','content_quality':'good'}]:
            with patch.object(remote,'corpus',return_value=DATA):
                row=remote.join_annotations('faroese',[entry],[0],{0:{'row':candidate}})[0]
            self.assertFalse(row['annotations_available'])
            self.assertNotIn('content_quality',row)
            self.assertEqual(row['preview'],'original')

    def test_source_page_crosses_boundaries_without_skipping(self):
        def hub(language,endpoint,**params):
            return {'rows':[{'row_idx':params['offset'],'row':{'id':params['config']+'-id','text':'text','source':params['config'],'token_count':2}}]}
        data={**DATA,'sources':[DATA['sources'][0],{'id':'b','domain':'Legal','records':1},{'id':'c','domain':'Other','records':10}]}
        with patch.object(remote,'corpus',return_value=data),patch.object(remote,'hub',side_effect=hub),patch.object(remote,'join_annotations',side_effect=lambda language,entries,positions:entries):
            result=remote.rows('faroese',filters=json.dumps({'domain':'Legal'}),offset=1,limit=2)
        self.assertEqual(result['total'],3)
        self.assertFalse(result['has_more'])
        self.assertEqual(result['rows'][0]['_config'],'a')
        self.assertEqual(result['rows'][0]['row_idx'],1)
        self.assertEqual(result['rows'][1]['_config'],'b')
        self.assertEqual(result['rows'][1]['row_idx'],0)

if __name__=='__main__':unittest.main()
