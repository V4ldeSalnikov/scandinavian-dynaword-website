"""Reproducible Danish fastText document-vector baseline.

All words in each original document are considered, without truncation. Known
word vectors are normalized and weighted by rank/(rank+500), then averaged and
normalized. This is a word-vector baseline, not a contextual passage model.
"""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import json
import re

import numpy as np

CACHE = Path(__file__).resolve().parents[1] / '.cache'
MODEL = CACHE / 'danish-fasttext'
WORDS = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
DIMENSIONS = 300


class Encoder:
    def __init__(self, folder=MODEL):
        self.vocabulary = {word: i for i, word in enumerate(json.loads((folder/'words.json').read_text()))}
        self.vectors = np.load(folder/'words.npy')

    def query_words(self, text):
        indices = list(dict.fromkeys(self.vocabulary[word] for word in WORDS.findall(text.lower()) if word in self.vocabulary))
        vectors = self.vectors[indices]
        weights = np.linalg.norm(vectors, axis=1)
        return vectors / np.maximum(weights[:, None], 1e-12), weights

    def concept_coverage(self, text, query_vectors, query_weights):
        indices = list({self.vocabulary[word] for word in WORDS.findall(text.lower()) if word in self.vocabulary})
        if not indices:
            return 0.0
        vectors = self.vectors[indices]
        vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1)[:, None], 1e-12)
        # Each query concept gets its best semantic match anywhere in the text.
        similarities = np.einsum('ij,kj->ik', vectors, query_vectors)
        coverage = np.clip(np.max(similarities, axis=0), 0, 1)
        return float(np.average(coverage, weights=query_weights))

    def encode(self, text):
        counts = Counter(WORDS.findall(text.lower()))
        matches = [(self.vocabulary[word], count) for word, count in counts.items() if word in self.vocabulary]
        if not matches:
            return np.zeros(self.vectors.shape[1], dtype=np.float32)
        indices, weights = zip(*matches)
        vector = np.einsum('i,ij->j', np.asarray(weights, dtype=np.float32), self.vectors[list(indices)])
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector


@lru_cache(maxsize=1)
def encoder():
    return Encoder()
