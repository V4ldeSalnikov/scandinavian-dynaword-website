"""Compact complete annotation indexes; original text stays in the source corpus."""
from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1] / '.cache/corpus-annotations'


def identity_hash(identifier):
    return int.from_bytes(hashlib.blake2b(identifier.encode('utf-8'), digest_size=8).digest(), 'little')


@lru_cache(maxsize=3)
def load(language, revision):
    path = ROOT / 'manifest.json'
    if not path.exists():
        return None
    manifest = json.loads(path.read_text())
    entry = manifest['languages'].get(language)
    if not entry or entry['revision'] != revision:
        return None
    filename = ROOT / entry['path']
    if filename.parent != ROOT or filename.stat().st_size != entry['bytes']:
        raise ValueError('Invalid annotation index')
    records = np.load(filename, mmap_mode='r', allow_pickle=False)
    if len(records) != entry['records']:
        raise ValueError('Incomplete annotation index')
    return entry, records


def select(index, allowed, annotations, bounds, offset, limit):
    """Count all matching records while retaining only the requested page."""
    entry, records = index
    total = 0
    page = []
    for source in entry['sources']:
        if source['id'] not in allowed:
            continue
        start, stop = source['offset'], source['offset'] + source['records']
        for begin in range(start, stop, 250_000):
            block = records[begin:min(begin + 250_000, stop)]
            mask = np.ones(len(block), dtype=bool)
            for field, value in annotations.items():
                mask &= block[field] == entry['labels'][field].get(value, 0)
            if 'min_tokens' in bounds:
                mask &= block['tokens'] >= bounds['min_tokens']
            if 'max_tokens' in bounds:
                mask &= block['tokens'] <= bounds['max_tokens']
            n = int(mask.sum())
            if n and total + n > offset and len(page) < limit:
                positions = np.flatnonzero(mask)
                skip = max(0, offset - total)
                page.extend((positions[skip:skip + limit - len(page)] + begin).tolist())
            total += n
    return page, total


def location(index, position):
    entry, records = index
    sources = entry['sources']
    source = sources[bisect_right([s['offset'] for s in sources], position) - 1]
    return source['id'], position - source['offset']


def annotations_at(index, position, identifier):
    entry, records = index
    row = records[position]
    if int(row['id_hash']) != identity_hash(identifier):
        raise ValueError('Text and annotation identities differ')
    return {field:next((value for value, code in labels.items() if code == int(row[field])), None)
            for field, labels in entry['labels'].items()}
