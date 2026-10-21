"""Restore the separately pinned Nordic annotation indexes after the base layer."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import requests
from restore_runtime import download


def restore(source, root):
    repo, revision = source['repo'], source['revision']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Annotation artifacts must be pinned.')
    base = f'https://huggingface.co/datasets/{repo}/resolve/{revision}/corpus-annotations/'
    response = requests.get(base+'manifest.json', timeout=(30, 90))
    response.raise_for_status()
    raw = response.content
    if hashlib.sha256(raw).hexdigest() != source['manifest_sha256']:
        raise ValueError('Annotation manifest checksum mismatch')
    manifest = response.json()
    if manifest['version'] != 1:
        raise ValueError('Unknown annotation index version')
    root.mkdir(parents=True, exist_ok=True)
    for language, entry in manifest['languages'].items():
        download(base, root, entry)
        print(f'Restored {language}: {entry["records"]:,} annotation rows', flush=True)
    (root/'manifest.json').write_bytes(raw)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, default=Path('.cache/corpus-annotations'))
    args=parser.parse_args()
    restore(json.loads(args.source.read_text()), args.destination)
