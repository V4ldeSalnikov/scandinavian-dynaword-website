import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import faiss
import numpy as np
from server import ann_search, semantic_search


class ApproximateSearchTests(unittest.TestCase):
    def tearDown(self):
        ann_search.source_lookup.cache_clear()

    def test_filter_is_applied_inside_index_before_candidate_limit(self):
        # A real IVF search: the nearest two vectors are excluded by metadata.
        vectors = np.array([[1, 0], [.99, .01], [.8, .2], [0, 1]], dtype=np.float32)
        index = faiss.IndexIVFFlat(faiss.IndexFlatIP(2), 2, 1, faiss.METRIC_INNER_PRODUCT)
        index.train(np.tile(vectors, (20, 1)))
        index.add_with_ids(vectors, np.arange(4, dtype=np.int64))
        with patch.object(ann_search, 'index_for', return_value=index):
            ids = ann_search.candidates(vectors[0], np.array([False, False, True, True]), limit=1)
            np.testing.assert_array_equal(ids, [2])
            self.assertEqual(len(ann_search.candidates(vectors[0], np.zeros(4, dtype=bool))), 0)

    def test_unsorted_record_ids_keep_their_original_vectors(self):
        vectors = np.array([[0, 1], [1, 0], [.6, .8]], dtype=np.float16)
        with patch.object(semantic_search, 'source_vectors', return_value=(vectors, np.array([8, 2, 5]))), patch.object(ann_search, 'candidates', return_value=np.array([5, 8, 2])):
            ranked, compared = ann_search.rank(np.array([1, 0], dtype=np.float32), ['fixture'], limit=2)
        self.assertEqual([r['record_no'] for r in ranked], [2, 5])
        self.assertAlmostEqual(ranked[0]['score'], 1)
        self.assertEqual(compared, 3)

    def test_stale_or_missing_index_cannot_be_used(self):
        semantic = {'revision': 'r', 'metadata_fingerprint': 'm', 'model': {'matrix_sha256': 's'}, 'records_with_vectors': 10}
        state = {'status': 'ready', 'revision': 'r', 'metadata_fingerprint': 'm', 'matrix_sha256': 's', 'records': 10}
        with tempfile.TemporaryDirectory() as folder, patch.object(ann_search, 'ROOT', Path(folder)):
            self.assertEqual(ann_search.status(semantic)['status'], 'unavailable')
            target = Path(folder) / 'semantic-ann'; target.mkdir()
            (target / 'index.faiss').touch()
            (target / 'manifest.json').write_text(json.dumps(state))
            self.assertEqual(ann_search.status(semantic)['status'], 'ready')
            self.assertEqual(ann_search.status({**semantic, 'revision': 'new'})['status'], 'stale')
            self.assertEqual(ann_search.status({**semantic, 'records_with_vectors': 9})['status'], 'stale')


if __name__ == '__main__':
    unittest.main()
