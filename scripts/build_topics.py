"""Fit Turftopic on a reproducible source-balanced sample; assign the full corpus.

Reuses the frozen full-document Danish fastText embeddings. The separate 2D UMAP
is a map of sampled documents, not a density estimate or a full-corpus embedding.
No corpus/index mutation: all outputs are revision-bound sidecars.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import sys

import duckdb
import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from threadpoolctl import threadpool_limits
from turftopic import Top2Vec
from turftopic.encoders.base import ExternalEncoder
from umap import UMAP

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.embeddings import Encoder
from server.text_search import original_texts
from scripts.build_semantic_index import write_json

CACHE = ROOT / '.cache'
FOLDER = CACHE / 'topics'
# Danish function words; the keyword vocabulary also excludes unknown fastText words.
STOP_WORDS = """ad af alle alt anden andet andre at bare begge blev bliver da de dem den denne dens der deres det dette dig din dine disse dog du efter eller en end ene eneste enhver er et få fik flere flest fordi fra før først gennem gøre gør gjorde god ham han hans har havde have hende hendes her hos hun hvad hvem hver hvilken hvilke hvis hvor hvordan hvorfor hvornår i ikke ind ingen intet jeg jer jeres jo kan kom komme kunne lad lidt lige man mange med meget men mens mere mig min mine mit mod må mellem ned nej noget nogen nogle nok nu når og også om op os over på samme sammen selv sig sin sine sit skal skulle som sådan så thi til ud uden under var ved vi vil ville vor være været år være www http https com dk samt dels blandt siden både nemlig dog kun""".split()


class DanishEncoder(ExternalEncoder):
    def __init__(self):
        self.model = Encoder()

    def encode(self, sentences, **kwargs):
        return np.asarray([self.model.encode(text) for text in sentences], dtype=np.float32)


def excerpt(text):
    if len(text) <= 6000:
        return text
    middle = len(text) // 2
    return text[:2000] + '\n' + text[middle-1000:middle+1000] + '\n' + text[-2000:]


def main(per_source=500, max_topics=28):
    FOLDER.mkdir(exist_ok=True)
    manifest = json.loads((CACHE/'manifest.json').read_text())
    semantic = json.loads((CACHE/'semantic_manifest.json').read_text())
    assert manifest['status'] == semantic['status'] == 'ready'
    with (CACHE/'corpus.duckdb').open('rb') as file:
        fingerprint = hashlib.file_digest(file, 'sha256').hexdigest()
    assert fingerprint == semantic['metadata_fingerprint']
    assert manifest['revision'] == semantic['revision']
    config = {'revision': manifest['revision'], 'metadata_fingerprint': fingerprint,
              'seed': 42, 'per_source': per_source, 'max_topics': max_topics,
              'turftopic_version': importlib.metadata.version('turftopic'), 'pipeline_version': 1}
    config_path = FOLDER/'config.json'
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise RuntimeError('Topic build configuration changed; use a fresh topics cache.')
    write_json(config_path, config)
    c = duckdb.connect(str(CACHE/'corpus.duckdb'), read_only=True)
    c.execute("SET threads=2; SET memory_limit='2GB'")
    sample_path = FOLDER/'sample.parquet'
    if not sample_path.exists():
        rng = np.random.default_rng(config['seed'])
        chosen, vectors = [], []
        for source in sorted(manifest['sources'], key=lambda s: s['id']):
            name = source['id']
            ids = np.load(CACHE/'semantic'/f'{name}.ids.npy', mmap_mode='r')
            matrix = np.load(CACHE/'semantic'/f'{name}.npy', mmap_mode='r')
            # A random permutation gives an exact without-replacement sample even
            # when some records have no vocabulary coverage.
            positions = rng.permutation(len(ids))
            positions = positions[:min(len(ids), per_source+1024)]
            candidates = np.asarray(matrix[positions], dtype=np.float32)
            valid = np.any(candidates, axis=1)
            chosen.extend(ids[positions[valid]][:per_source].tolist())
            vectors.extend(candidates[valid][:per_source])
        order = np.argsort(chosen)
        chosen = np.asarray(chosen)[order]
        vectors = np.asarray(vectors)[order]
        rows = c.execute('SELECT record_no,source,id FROM records WHERE record_no IN (SELECT unnest(?)) ORDER BY record_no', [chosen.tolist()]).fetchall()
        assert [r[0] for r in rows] == chosen.tolist()
        documents, previews = [], []
        print(f'Reading {len(rows):,} sampled originals across all sources…', flush=True)
        for i, text in enumerate(original_texts((source, identifier) for _, source, identifier in rows)):
            if text is None:
                raise RuntimeError('Missing original text in the full-text index')
            documents.append(excerpt(text))
            previews.append(' '.join(text[:1000].split())[:260])
            if (i+1) % 2500 == 0:
                print(f'  {i+1:,} originals read', flush=True)
        np.save(FOLDER/'sample_vectors.npy', vectors)
        pq.write_table(pa.table({'record_no': chosen, 'document': documents, 'preview': previews}), FOLDER/'sample.partial.parquet')
        (FOLDER/'sample.partial.parquet').replace(sample_path)
    sample = pq.read_table(sample_path).to_pydict()
    vectors = np.load(FOLDER/'sample_vectors.npy')
    model_path = FOLDER/'model.joblib'
    if not model_path.exists():
        encoder = DanishEncoder()
        vectorizer = CountVectorizer(stop_words=STOP_WORDS, min_df=5, max_df=.5,
                                     max_features=18000, token_pattern=r'(?u)\b[^\W\d_]{3,}\b')
        # Restrict terms to words represented by the same Danish encoder.
        vectorizer.fit(sample['document'])
        vocabulary = sorted(set(vectorizer.get_feature_names_out()) & encoder.model.vocabulary.keys())
        vectorizer = CountVectorizer(vocabulary=vocabulary, token_pattern=r'(?u)\b[^\W\d_]{3,}\b')
        model = Top2Vec(encoder=encoder, vectorizer=vectorizer,
                       dimensionality_reduction=UMAP(n_components=5, n_neighbors=20, min_dist=0,
                                                    metric='cosine', random_state=42, n_jobs=1),
                       clustering=HDBSCAN(min_cluster_size=40, min_samples=10, cluster_selection_method='leaf'),
                       random_state=42)
        print('Fitting Turftopic Top2Vec (5D UMAP + HDBSCAN)…', flush=True)
        model.fit_predict(sample['document'], embeddings=vectors)
        discovered = len([t for t in model.classes_ if t != -1])
        print(f'Discovered {discovered} topics', flush=True)
        if discovered < 2:
            raise RuntimeError('Insufficient topic structure; inspect the model before publishing.')
        if discovered > max_topics:
            model.reduce_topics(n_reduce_to=max_topics)
        joblib.dump(model, FOLDER/'model.partial.joblib', compress=3)
        (FOLDER/'model.partial.joblib').replace(model_path)
    else:
        model = joblib.load(model_path)
    classes = np.asarray(model.classes_)
    valid_columns = np.flatnonzero(classes != -1)
    topic_ids = classes[valid_columns].astype(np.int16)
    # This is the centroid representation used by Turftopic.transform; validate
    # the vectorized whole-corpus assignment against the library, not a surrogate.
    centroids = np.asarray([vectors[model.labels_ == topic].mean(axis=0) for topic in topic_ids])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    expected = model.transform([], embeddings=vectors[:128])[:, valid_columns]
    actual = vectors[:128] @ centroids.T / np.linalg.norm(vectors[:128], axis=1, keepdims=True)
    assert np.allclose(expected, actual, atol=1e-5)
    np.save(FOLDER/'centroids.npy', centroids)
    coordinates_path = FOLDER/'coordinates.npy'
    if not coordinates_path.exists():
        print('Projecting sampled records into a separate 2D UMAP map…', flush=True)
        coordinates = UMAP(n_components=2, n_neighbors=20, min_dist=.12, metric='cosine',
                           random_state=42, n_jobs=1).fit_transform(vectors)
        assert np.isfinite(coordinates).all()
        np.save(coordinates_path, coordinates)
    coordinates = np.load(coordinates_path)
    schema = pa.schema([('record_no', pa.int64()), ('topic_id', pa.int16()), ('topic_similarity', pa.float32())])
    all_labels = np.full(manifest['records'], -2, dtype=np.int16)
    all_scores = np.zeros(manifest['records'], dtype=np.float32)
    seen = np.zeros(manifest['records'], dtype=bool)
    print('Assigning every corpus vector to its nearest learned topic…', flush=True)
    for source in manifest['sources']:
        name = source['id']
        ids = np.load(CACHE/'semantic'/f'{name}.ids.npy', mmap_mode='r')
        matrix = np.load(CACHE/'semantic'/f'{name}.npy', mmap_mode='r')
        for start in range(0, len(ids), 32768):
            row_ids = ids[start:start+32768]
            v = np.asarray(matrix[start:start+32768], dtype=np.float32)
            norms = np.linalg.norm(v, axis=1)
            scores = (v @ centroids.T) / np.maximum(norms[:, None], 1e-12)
            best = np.argmax(scores, axis=1)
            labels = topic_ids[best].copy()
            labels[norms == 0] = -1
            assert not np.any(seen[row_ids])
            all_labels[row_ids] = labels
            all_scores[row_ids] = scores[np.arange(len(v)), best]
            seen[row_ids] = True
        print(f'  {name}: {len(ids):,} assigned', flush=True)
    assert seen.all() and np.isfinite(all_scores).all()
    assert np.count_nonzero(all_labels != -1) == semantic['records_with_vectors']
    pq.write_table(pa.Table.from_arrays([pa.array(np.arange(len(all_labels))), pa.array(all_labels), pa.array(all_scores)], schema=schema), FOLDER/'assignments.partial.parquet')
    (FOLDER/'assignments.partial.parquet').replace(FOLDER/'assignments.parquet')
    sample_ids = np.asarray(sample['record_no'])
    pq.write_table(pa.table({'record_no': sample_ids, 'x': np.round(coordinates[:, 0], 4),
                            'y': np.round(coordinates[:, 1], 4), 'preview': sample['preview']}), FOLDER/'points.parquet')
    # Centroid-nearest keywords can repeat generic words with this word-vector
    # baseline. Turftopic's c-TF-IDF highlights terms distinctive to each fitted
    # cluster. This changes only the displayed keywords, not corpus assignment.
    model.estimate_components(feature_importance='c-tf-idf')
    topics = []
    for topic_id, words in model.get_topics(top_k=10):
        if topic_id == -1:
            continue
        topics.append({'id': int(topic_id), 'name': ' · '.join(word for word, _ in words[:3]),
                       'keywords': [{'word': str(word), 'score': round(float(score), 5)} for word, score in words],
                       'fit_records': int(np.count_nonzero(model.labels_ == topic_id)),
                       'records': int(np.count_nonzero(all_labels == topic_id))})
    sample_sources = c.execute('SELECT source,count(*) FROM records WHERE record_no IN (SELECT unnest(?)) GROUP BY source ORDER BY source', [sample['record_no']]).fetchall()
    assert len(sample_sources) == len(manifest['sources'])
    state = {**config, 'status': 'ready', 'records': manifest['records'],
             'assigned': semantic['records_with_vectors'], 'unassigned': int(np.count_nonzero(all_labels == -1)),
             'sample_records': len(sample_ids), 'sample_sources': dict(sample_sources),
             'fit_outliers': int(np.count_nonzero(model.labels_ == -1)),
             'topics': sorted(topics, key=lambda t: -t['records']),
             'keyword_method': 'Turftopic c-TF-IDF on fitted clusters; assignment remains document-centroid cosine.',
             'model': 'Turftopic Top2Vec · Danish fastText · UMAP + HDBSCAN',
             'method': f'Fit on up to {per_source} seeded random vector-bearing records per source. Topic keywords use c-TF-IDF on up to 6,000 original characters (beginning, middle, end); document vectors cover all original text. HDBSCAN clusters in 5D UMAP; separate 2D UMAP for the map. Full-corpus assignment uses maximum cosine to a non-noise topic centroid, equivalent to Turftopic.transform. Assignments are automatic, single-topic approximations, not validated annotations. Cosine similarity is not confidence. Zero vectors remain unassigned. Map dot density does not represent corpus prevalence.',
             'reference': 'https://x-tabdeveloping.github.io/turftopic/tutorials/arxiv_ml/'}
    write_json(CACHE/'topics_manifest.json', state)
    c.close()
    print(f"READY: {len(topics)} topics, {len(sample_ids):,} map points, all {len(all_labels):,} records accounted for", flush=True)
    for topic in state['topics']:
        print(f"  {topic['id']:3}: {topic['name']} — {topic['records']:,}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--per-source', type=int, default=500)
    parser.add_argument('--max-topics', type=int, default=28)
    args = parser.parse_args()
    with threadpool_limits(limits=3):
        main(args.per_source, args.max_topics)
