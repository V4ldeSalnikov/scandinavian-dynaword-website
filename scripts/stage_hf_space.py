"""Assemble the API-only Space from tracked source and a pinned artifact commit."""
import argparse
import json
from pathlib import Path
import re
import shutil


def stage(output):
    root = Path(__file__).resolve().parents[1]
    config = root / 'deploy/huggingface'
    source = json.loads((config / 'runtime-source.json').read_text())
    if not re.fullmatch(r'[0-9a-f]{40}', source['revision']):
        raise ValueError('Pin the completely uploaded artifact repository first.')
    output.mkdir(parents=True, exist_ok=True)
    for filename, target in [('Dockerfile', 'Dockerfile'), ('SPACE.md', 'README.md'), ('runtime-source.json', 'runtime-source.json')]:
        shutil.copyfile(config / filename, output / target)
    (output / 'server').mkdir(exist_ok=True)
    for path in (root / 'server').glob('*.py'):
        if not path.name.startswith('test_'):
            shutil.copyfile(path, output / 'server' / path.name)
    shutil.copyfile(root / 'server/requirements.txt', output / 'server/requirements.txt')
    (output / 'scripts').mkdir(exist_ok=True)
    shutil.copyfile(root / 'scripts/restore_runtime.py', output / 'scripts/restore_runtime.py')
    print(f'Space staged at {output}; artifacts: {source["repo"]}@{source["revision"]}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.cache/hf-space'))
    args = parser.parse_args()
    stage(args.output)
