"""Selection aggregates over complete, revision-pinned record metadata."""
from collections import defaultdict
from functools import lru_cache
import json
import threading

import numpy as np
from . import annotation_index, corpus_search

BOUNDS = np.array([0] + [2 ** p for p in range(4, 32)] + [2 ** 32], dtype=np.uint64)
SCAN_LOCK = threading.Semaphore(1)


def aggregate(data, sources, annotations, bounds, annotation, index=None):
    groups, labels, histogram = [], defaultdict(int), np.zeros(len(BOUNDS)-1, dtype=np.int64)
    annotated = covered = 0
    annotation_available = bool(data.get('annotation_distributions'))
    if index is None:
        # Published counts are exact for source/domain selections. Intersections
        # need record metadata and must never fall back to unfiltered totals.
        if annotations or bounds:
            raise ValueError('Selection statistics are waiting for the complete record index.')
        for source in sources:
            groups.append({'name':source['id'], 'domain':source['domain'], 'records':source['records'], 'tokens':source['tokens']})
            annotated += source.get('annotated') or 0
            distribution = (source.get('annotation_distributions') or {}).get(annotation, {})
            for value, count in distribution.items():
                labels[value] += count
                covered += count
            if annotation_available:
                labels['__missing__'] += source['records'] - sum(distribution.values())
    else:
        entry, records = index
        offsets = {s['id']:s for s in entry['sources']}
        for source in sources:
            span = offsets[source['id']]
            count = tokens = 0
            for start in range(span['offset'], span['offset'] + span['records'], 250_000):
                block = records[start:min(start + 250_000, span['offset'] + span['records'])]
                mask = np.ones(len(block), dtype=bool)
                for field, value in annotations.items():
                    mask &= block[field] == entry['labels'][field].get(value, 0)
                for key, comparison in [('min_tokens', np.greater_equal), ('max_tokens', np.less_equal)]:
                    if key in bounds:
                        mask &= comparison(block['tokens'], bounds[key])
                selected = block[mask]
                count += len(selected)
                tokens += int(selected['tokens'].sum(dtype=np.uint64))
                histogram += np.histogram(selected['tokens'], bins=BOUNDS)[0]
                if annotation_available:
                    annotated += int(np.count_nonzero(selected['content_quality']))
                    counts = np.bincount(selected[annotation], minlength=256)
                    covered += len(selected) - int(counts[0])
                    labels['__missing__'] += int(counts[0])
                    for value, code in entry['labels'][annotation].items():
                        labels[value] += int(counts[code])
            if count:
                groups.append({'name':source['id'], 'domain':source['domain'], 'records':count, 'tokens':tokens})
    domains = {}
    for group in groups:
        target = domains.setdefault(group['domain'], {'name':group['domain'], 'records':0, 'tokens':0})
        for metric in ('records', 'tokens'):
            target[metric] += group[metric]
    return {
        'totals': {'records':sum(s['records'] for s in groups), 'tokens':sum(s['tokens'] for s in groups), 'sources':len(groups), 'annotated':annotated},
        'sources':groups, 'domains':list(domains.values()),
        'annotations':[{'name':name, 'records':count, 'tokens':0} for name,count in labels.items() if count],
        'annotation':annotation, 'annotation_covered':covered, 'annotations_available':annotation_available,
        'histogram_available':index is not None,
        'histogram':[{'min':int(a), 'max':int(b)-1, 'records':int(count)} for a,b,count in zip(BOUNDS[:-1], BOUNDS[1:], histogram)] if index is not None else [],
    }


@lru_cache(maxsize=96)
def cached(language, revision, sources_json, annotations_json, bounds_json, annotation, ready):
    from .remote_corpora import corpus
    data = corpus(language)
    if data['revision'] != revision:
        raise ValueError('The dataset release changed. Reload the explorer.')
    selected = set(json.loads(sources_json))
    sources = [s for s in data['sources'] if s['id'] in selected]
    index = annotation_index.load(language, revision)
    with SCAN_LOCK:
        if index is None and ready:
            entry, _, metadata = corpus_search.snapshot(str(corpus_search.directory(data)))
            index = (entry, metadata)
        return aggregate(data, sources, json.loads(annotations_json), json.loads(bounds_json), annotation, index)
