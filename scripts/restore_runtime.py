"""Restore and verify a pinned public serving snapshot without Hub credentials."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import time
from urllib.parse import quote

import requests


def file_matches(path, entry):
    if not path.is_file() or path.stat().st_size != entry['bytes']:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256']


def destination(root, entry):
    name = PurePosixPath(entry['path'])
    if name.is_absolute() or '..' in name.parts or not name.parts:
        raise ValueError('Unsafe path in runtime inventory')
    path = (root / str(name)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Runtime inventory escapes its destination')
    return path


def download(base, root, entry):
    path = destination(root, entry)
    if file_matches(path, entry):
        return entry['bytes']
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.download')
    for attempt in range(5):
        try:
            digest = hashlib.sha256()
            size = 0
            with requests.get(base + quote(entry['path'], safe='/'), stream=True, timeout=(30, 180)) as response:
                response.raise_for_status()
                with partial.open('wb') as stream:
                    for chunk in response.iter_content(4 * 1024 * 1024):
                        stream.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                        if size > entry['bytes']:
                            raise ValueError(f"Unexpected size: {entry['path']}")
            if size != entry['bytes'] or digest.hexdigest() != entry['sha256']:
                raise ValueError(f"Integrity check failed: {entry['path']}")
            partial.replace(path)
            return size
        except (requests.RequestException, ValueError):
            partial.unlink(missing_ok=True)
            if attempt == 4:
                raise
            time.sleep(min(2 ** attempt, 16))


def restore(source, root, workers=4):
    repo, revision = source['repo'], source['revision']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Use a Hub dataset repository and a pinned 40-character commit SHA.')
    base = f'https://huggingface.co/datasets/{repo}/resolve/{revision}/'
    response = requests.get(base + 'runtime.json', timeout=(30, 90))
    response.raise_for_status()
    inventory = response.json()
    if inventory['version'] != 1 or inventory['dataset'] != 'danish-foundation-models/danish-dynaword':
        raise ValueError('Unexpected runtime inventory')
    entries = inventory['files']
    names = [entry['path'] for entry in entries]
    if len(names) != len(set(names)) or 'manifest.json' not in names:
        raise ValueError('Incomplete or duplicate runtime inventory')
    for entry in entries:
        destination(root, entry)
    root.mkdir(parents=True, exist_ok=True)
    # The ready manifest is installed last, so interrupted restores never look ready.
    (root / 'manifest.json').unlink(missing_ok=True)
    ready = next(entry for entry in entries if entry['path'] == 'manifest.json')
    total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [pool.submit(download, base, root, entry) for entry in entries if entry != ready]
        for i, future in enumerate(as_completed(pending), start=1):
            total += future.result()
            if i % 10 == 0 or i == len(pending):
                print(f'Restored {i}/{len(pending)} artifacts; {total/1e9:.2f}/{inventory["bytes"]/1e9:.2f} GB verified', flush=True)
    download(base, root, ready)
    (root / 'texts').mkdir(exist_ok=True)
    (root / 'runtime_source.json').write_text(json.dumps(source, indent=2) + '\n')
    print(f'Ready: {inventory["records"]:,} records at dataset revision {inventory["revision"]}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', default='.cache', type=Path)
    parser.add_argument('--workers', default=4, type=int)
    args = parser.parse_args()
    restore(json.loads(args.source.read_text()), args.destination, args.workers)
