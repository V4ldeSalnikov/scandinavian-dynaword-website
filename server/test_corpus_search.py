import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import faiss
from faiss.contrib.ondisk import merge_ondisk
import numpy as np
import tantivy
from fastapi import HTTPException

from server import corpus_search as search
from server import remote_ann
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
        (self.path / 'vectors').mkdir()
        vectors = FakeModel().encode(self.texts).astype('<f2')
        vectors[:2].tofile(self.path / 'vectors/a.f16')
        vectors[2:].tofile(self.path / 'vectors/b.f16')
        faiss.omp_set_num_threads(1)
        ann = faiss.IndexIVFFlat(faiss.IndexFlatIP(256), 256, 1, faiss.METRIC_INNER_PRODUCT)
        ann.train(np.tile(np.eye(1, 256, dtype=np.float32), (64, 1)))
        faiss.write_index(ann, str(self.path / 'trained.faiss'))
        merged = faiss.clone_index(ann)
        ann.add_with_ids(FakeModel().encode(self.texts), np.arange(4, dtype=np.int64))
        faiss.write_index(ann, str(self.path / 'part.faiss'))
        merge_ondisk(merged, [str(self.path / 'part.faiss')], str(self.path / 'index.ivfdata'))
        faiss.write_index(merged, str(self.path / 'index.faiss'))

    def tearDown(self):
        search.snapshot.cache_clear(); search.vector_index.cache_clear(); search.semantic_results.cache_clear()
        search.ranked_record.cache_clear()
        remote_ann.prototype.cache_clear()
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

    def test_reader_locks_are_local_and_index_data_stays_on_the_mount(self):
        source = self.path / 'fulltext'
        before = {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
        search.text_search(self.data, 'energy', {'a', 'b'}, {}, {})
        reader = search.reader_directory(self.path)
        self.assertNotEqual(reader, source)
        self.assertTrue((reader / 'meta.json').is_symlink())
        self.assertTrue((reader / '.tantivy-meta.lock').exists())
        self.assertFalse((reader / '.tantivy-meta.lock').is_symlink())
        self.assertEqual(before, {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()})

    def test_semantic_search_respects_annotation_source_and_length_filters(self):
        with patch.object(search, 'encoder', return_value=FakeModel()):
            result = search.semantic_search(self.data, 'energy', {'a', 'b'}, {'content_quality': 'good'}, {'min_tokens': 20})
            self.assertEqual([r['id'] for r in result['rows']], ['2'])
            result = search.semantic_search(self.data, 'energy', {'a'}, {'content_quality': 'good'}, {'min_tokens': 20})
            self.assertEqual(result['total'], 0)

    def test_remote_blocks_match_faiss_with_filters_and_small_chunks(self):
        local = faiss.read_index(str(self.path / 'index.faiss'))
        query = FakeModel().encode(['energy'])[0]
        allowed = np.asarray([True, False, True, False])
        bitmap = np.packbits(allowed, bitorder='little')
        selector = faiss.IDSelectorBitmap(len(bitmap), faiss.swig_ptr(bitmap))
        expected_scores, expected_ids = local.search(query[None, :], 4,
            params=faiss.SearchParametersIVF(nprobe=1, sel=selector))
        with patch.object(remote_ann, 'BLOCK_RECORDS', 1):
            scores, ids = remote_ann.candidates(str(self.path), search.vector_index(str(self.path)), query, 1, allowed, 4)
        expected = {int(i):float(s) for s,i in zip(expected_scores[0], expected_ids[0]) if i >= 0}
        self.assertEqual({int(i):float(s) for s,i in zip(scores, ids)}, expected)

    def test_pq_blocks_preserve_ranked_results_across_partitions(self):
        folder = self.root / 'pq'; folder.mkdir()
        rng = np.random.default_rng(42)
        vectors = rng.normal(size=(256, 256)).astype('float32'); faiss.normalize_L2(vectors)
        ann = faiss.index_factory(256, 'IVF4,PQ8x4', faiss.METRIC_INNER_PRODUCT)
        ann.cp.niter = ann.pq.cp.niter = 3
        ann.cp.min_points_per_centroid = ann.pq.cp.min_points_per_centroid = 1
        ann.train(vectors)
        faiss.write_index(ann, str(folder / 'trained.faiss'))
        merged = faiss.clone_index(ann)
        ann.add(vectors[:96]); faiss.write_index(ann, str(folder / 'part.faiss'))
        merge_ondisk(merged, [str(folder / 'part.faiss')], str(folder / 'index.ivfdata'))
        faiss.write_index(merged, str(folder / 'index.faiss'))
        metadata = faiss.read_index(str(folder / 'index.faiss'), faiss.IO_FLAG_SKIP_IVF_DATA)
        allowed = np.arange(96) % 3 == 0
        bitmap = np.packbits(allowed, bitorder='little')
        selector = faiss.IDSelectorBitmap(len(bitmap), faiss.swig_ptr(bitmap))
        expected_scores, expected_ids = ann.search(vectors[130:131], 17,
            params=faiss.SearchParametersIVF(nprobe=3, sel=selector))
        with patch.object(remote_ann, 'BLOCK_RECORDS', 19):
            scores, ids = remote_ann.candidates(str(folder), metadata, vectors[130], 3, allowed, 17)
        np.testing.assert_array_equal(ids, expected_ids[0])
        np.testing.assert_allclose(scores, expected_scores[0], atol=1e-5)

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
