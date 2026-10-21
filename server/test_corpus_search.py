import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import faiss
import numpy as np
import tantivy
from fastapi import HTTPException

from server import corpus_search as search
from server import remote_corpora as remote
from scripts.build_corpus_search import metadata_rows


class FakeModel:
    def encode(self, texts, max_length=None):
        vectors = np.zeros((len(texts), 256), dtype=np.float32)
        for i, text in enumerate(texts):
            vectors[i, 0 if 'energy' in text else 1] = 1
        return vectors


class CorpusSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(search, 'ROOT', self.root); self.patch.start()
        self.data = {'id': 'faroese', 'revision': 'test', 'records': 4}
        self.path = self.root / 'faroese/test'; self.path.mkdir(parents=True)
        self.state = {'format': 1, 'status': 'ready', 'revision': 'test', 'model_revision': search.MODEL_REVISION,
                      'records': 4, 'vectors': 4, 'sources': [{'id': 'a', 'offset': 0, 'records': 2},
                      {'id': 'b', 'offset': 2, 'records': 2}],
                      'labels': {field: {'good': 1, 'poor': 2} for field in search.FIELDS}}
        (self.path / 'manifest.json').write_text(json.dumps(self.state))
        folder = self.path / 'fulltext'; folder.mkdir()
        index = tantivy.Index(search.schema(), path=str(folder))
        writer = index.writer(heap_size=20_000_000, num_threads=1)
        metadata = np.zeros(4, dtype=search.METADATA_DTYPE)
        self.texts = ['energy wind power', 'energy solar power', 'energy water power', 'music and literature']
        for number, text in enumerate(self.texts):
            source = 'a' if number < 2 else 'b'
            quality = 'good' if number % 2 == 0 else 'poor'
            data = {field: '__missing__' for field in search.FIELDS}
            data.update(text=text, id=str(number).encode(), source=source, domain='News',
                        record_no=number, row_index=number % 2, token_count=(number + 1) * 10,
                        content_quality=quality, educational_value=quality)
            writer.add_document(tantivy.Document.from_dict(data, index.schema))
            metadata[number]['tokens'] = (number + 1) * 10
            metadata[number]['content_quality'] = 1 if quality == 'good' else 2
            metadata[number]['educational_value'] = 1 if quality == 'good' else 2
        writer.commit(); writer.wait_merging_threads()
        metadata.tofile(self.path / 'metadata.bin')
        faiss.omp_set_num_threads(1)
        ann = faiss.IndexIVFFlat(faiss.IndexFlatIP(256), 256, 1, faiss.METRIC_INNER_PRODUCT)
        ann.train(np.tile(np.eye(1, 256, dtype=np.float32), (64, 1)))
        ann.add_with_ids(FakeModel().encode(self.texts), np.arange(4, dtype=np.int64))
        faiss.write_index(ann, str(self.path / 'index.faiss'))

    def tearDown(self):
        search.snapshot.cache_clear(); search.vector_index.cache_clear(); search.semantic_results.cache_clear()
        self.patch.stop(); self.temp.cleanup()

    def test_ready_requires_complete_matching_release_and_model(self):
        self.assertTrue(search.status(self.data)['text'])
        for key, value in [('records', 3), ('revision', 'other'), ('model_revision', 'other'), ('status', 'building')]:
            (self.path / 'manifest.json').write_text(json.dumps({**self.state, key: value}))
            self.assertFalse(search.status(self.data)['semantic'])

    def test_keyword_filters_intersect_before_counting_and_pagination(self):
        result = search.text_search(self.data, 'energy', {'a', 'b'}, {'content_quality': 'good', 'educational_value': 'good'}, {}, 1, 1)
        self.assertEqual(result['total'], 2)
        self.assertEqual(len(result['rows']), 1)
        self.assertFalse(result['has_more'])
        result = search.text_search(self.data, 'energy', {'b'}, {}, {'max_tokens': 35})
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['rows'][0]['id'], '2')

    def test_full_browsing_crosses_source_boundary_and_jumps_to_final_record(self):
        result = search.text_search(self.data, '', {'a', 'b'}, {}, {}, 1, 2)
        self.assertEqual([r['id'] for r in result['rows']], ['1', '2'])
        self.assertEqual(result['total'], 4)
        last = search.text_search(self.data, '', {'a', 'b'}, {}, {}, 3, 30)
        self.assertEqual([r['id'] for r in last['rows']], ['3'])
        self.assertFalse(last['has_more'])
        filtered = search.text_search(self.data, '', {'a', 'b'}, {'content_quality': 'good'}, {}, 0, 30)
        self.assertEqual([r['id'] for r in filtered['rows']], ['0', '2'])

    def test_original_identity_is_checked(self):
        self.assertEqual(search.original(self.data, 'b', 0, '2')['text'], self.texts[2])
        with self.assertRaises(ValueError):
            search.original(self.data, 'b', 0, 'wrong')

    def test_semantic_search_respects_annotation_source_and_length_filters(self):
        with patch.object(search, 'encoder', return_value=FakeModel()):
            result = search.semantic_search(self.data, 'energy', {'a', 'b'}, {'content_quality': 'good'}, {'min_tokens': 20})
            self.assertEqual([r['id'] for r in result['rows']], ['2'])
            result = search.semantic_search(self.data, 'energy', {'a'}, {'content_quality': 'good'}, {'min_tokens': 20})
            self.assertEqual(result['total'], 0)

    def test_build_rejects_mismatched_annotation_id(self):
        dtype = np.dtype([('id_hash', '<u8'), ('tokens', '<u4')] + [(f, 'u1') for f in search.FIELDS])
        annotations = np.zeros(1, dtype=dtype)
        annotations[0]['id_hash'] = int.from_bytes(hashlib.blake2b(b'expected', digest_size=8).digest(), 'little')
        annotations[0]['tokens'] = 10
        with self.assertRaises(ValueError):
            metadata_rows({'id': 'a', 'offset': 0}, 0, [{'id': 'different', 'token_count': 10}], self.state, annotations)

    def test_api_rejects_search_until_complete(self):
        with patch.object(remote, 'corpus', return_value=self.data), patch.object(search, 'status', return_value={'text': False, 'semantic': False}):
            with self.assertRaises(HTTPException) as error:
                remote.search('faroese', 'energy', 'semantic', '{}', 0, 30)
            self.assertEqual(error.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
