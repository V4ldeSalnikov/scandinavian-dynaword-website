import unittest
from unittest.mock import patch
import numpy as np
from server import semantic_search
from server.embeddings import Encoder


class SemanticSearchTests(unittest.TestCase):
    def test_multiple_query_concepts_beat_a_single_word_fragment(self):
        model = Encoder.__new__(Encoder)
        model.vocabulary = {'energi': 0, 'klima': 1, 'vedvarende': 2, 'solkraft': 3}
        model.vectors = np.array([[1, 0], [0, 1], [.8, .2], [.9, .1]], dtype=np.float32)
        query, weights = model.query_words('energi klima')
        fragment = model.concept_coverage('vedvarende', query, weights)
        relevant = model.concept_coverage('solkraft klima', query, weights)
        self.assertGreater(relevant, fragment)
        # Semantic similarity works even when the document uses another word.
        self.assertGreater(model.concept_coverage('solkraft', *model.query_words('energi')), .9)

    def test_vectors_rank_by_similarity_without_word_overlap(self):
        vectors = np.array([[0, 1], [1, .1], [.6, .8], [0, 0]], dtype=np.float16)
        with patch.object(semantic_search, 'source_vectors', return_value=(vectors, np.arange(4))):
            hits, compared = semantic_search.rank(np.array([1, 0]), ['example'], limit=2)
        self.assertEqual([r['record_no'] for r in hits], [1, 2])
        self.assertEqual(compared, 3)  # Missing vectors do not count as searchable.

    def test_filters_apply_before_top_results(self):
        vectors = np.array([[1, 0], [.8, .2], [0, 1]], dtype=np.float16)
        with patch.object(semantic_search, 'source_vectors', return_value=(vectors, np.arange(3))):
            hits, compared = semantic_search.rank(np.array([1, 0]), ['example'], np.array([False, True, False]))
        self.assertEqual([r['record_no'] for r in hits], [1])
        self.assertEqual(compared, 1)


if __name__ == '__main__':
    unittest.main()
