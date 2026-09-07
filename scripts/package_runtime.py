"""Stage only immutable serving artifacts, using hard links to avoid duplication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_snapshot(cache, manifest):
    for name, count_field in [('search_manifest.json', 'records'), ('semantic_manifest.json', 'records_processed'), ('topics_manifest.json', 'records')]:
        state = json.loads((cache / name).read_text())
        if state.get('status') != 'ready' or state.get('revision') != manifest['revision'] or state.get(count_field) != manifest['records']:
            raise ValueError(f'{name} does not cover the complete, ready corpus snapshot.')
    semantic = json.loads((cache / 'semantic_manifest.json').read_text())
    topics = json.loads((cache / 'topics_manifest.json').read_text())
    if topics.get('metadata_fingerprint') != semantic.get('metadata_fingerprint') or topics.get('assigned') != semantic.get('records_with_vectors'):
        raise ValueError('Topic assignments and document vectors belong to different snapshots.')


def package(cache, output):
    cache, output = Path(cache).resolve(), Path(output).resolve()
    manifest = json.loads((cache / 'manifest.json').read_text())
    if manifest['status'] != 'ready':
        raise ValueError('Finish preparing the complete corpus first.')
    check_snapshot(cache, manifest)
    paths = [cache / name for name in ['corpus.duckdb', 'manifest.json', 'search_manifest.json', 'semantic_manifest.json', 'topics_manifest.json']]
    paths += [p for p in (cache / 'fulltext').iterdir() if p.is_file() and not p.name.endswith('.lock')]
    paths += [p for p in (cache / 'semantic').glob('*.npy') if '.partial' not in p.name]
    paths += list((cache / 'danish-fasttext').iterdir())
    paths += [cache / 'topics' / name for name in ['assignments.parquet', 'points.parquet']]
    output.mkdir(parents=True, exist_ok=True)
    attributes = Path(__file__).resolve().parents[1] / 'deploy/huggingface/index.gitattributes'
    shutil.copyfile(attributes, output / '.gitattributes')
    entries = []
    for i, source in enumerate(sorted(paths)):
        relative = source.relative_to(cache)
        dest = output / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            os.link(source, dest)
        if not os.path.samefile(source, dest):
            raise ValueError(f'Staging path is not the expected immutable source: {relative}')
        entries.append({'path': str(relative), 'bytes': source.stat().st_size, 'sha256': digest(source)})
        if i % 20 == 0:
            print(f'Hashed {i+1}/{len(paths)} artifacts', flush=True)
    inventory = {'version': 1, 'dataset': manifest['dataset'], 'revision': manifest['revision'], 'records': manifest['records'], 'bytes': sum(x['bytes'] for x in entries), 'files': entries}
    (output / 'runtime.json').write_text(json.dumps(inventory, indent=2) + '\n')
    (output / 'README.md').write_text(f'''---
language: da
pretty_name: Danish Dynaword explorer serving indexes
tags:
  - dynaword
  - search
  - topic-modeling
  - derived-data
viewer: false
---

# Danish Dynaword explorer serving indexes

Immutable runtime artifacts for [the explorer](https://v4ldesalnikov.github.io/scandinavian-dynaword-website/).
Source code and build instructions: https://github.com/V4ldeSalnikov/scandinavian-dynaword-website.

Source: [{manifest['dataset']}](https://huggingface.co/datasets/{manifest['dataset']}/tree/{manifest['revision']}).
Pinned source revision: `{manifest['revision']}`. Coverage: {manifest['records']:,} records across {len(manifest['sources'])} sources.
`runtime.json` records SHA-256 checksums and sizes for every serving artifact.
The text index includes original document text. Annotations are model predictions; PII flags do not imply anonymization.

## Attribution and licenses

Original texts and annotations retain their original licenses and restrictions, which vary by source.
`manifest.json` lists each collection's license and links to its original dataset card; consult those cards before reusing content.
This repository does not relicense the underlying corpus.

The fastText vocabulary vectors and derived document vectors use **CC BY-SA 3.0**:
Grave, Bojanowski, Gupta, Joulin, Mikolov (2018), *Learning Word Vectors for 157 Languages*.
Original vectors: https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.da.300.vec.gz.
The vocabulary is limited to the first 100,000 entries, normalized and weighted as described in `danish-fasttext/definition.json`.
Derived document vectors, reduced topic assignments and map coordinates were produced by the explorer's build scripts.
`topics_manifest.json` documents the Turftopic run, sampling, projection, model limitations and full-corpus assignment coverage.

## Contents

- `corpus.duckdb`: all document metadata and annotations.
- `fulltext/`: Tantivy BM25 index with stored original texts.
- `semantic/`, `danish-fasttext/`: full-corpus search vectors and query vocabulary.
- `topics/`: assignments for all usable document vectors and a sampled interactive map.
- `*_manifest.json`: coverage and reproducibility information.

Training caches, logs, temporary files and credentials are excluded.
''')
    print(f"Staged {len(entries)} files, {inventory['bytes']/1e9:.2f} GB at {output}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='.cache')
    parser.add_argument('--output', default='.cache/hf-runtime')
    args = parser.parse_args()
    package(args.cache, args.output)
