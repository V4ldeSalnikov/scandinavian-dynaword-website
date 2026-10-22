#!/usr/bin/env python3
"""Launch bounded, resumable HF CPU indexing jobs; keep a local cost ledger.

Requires huggingface_hub==2.2.0 and an existing local login. No token is sent to
the job: managed volumes provide its public inputs and output bucket. Run with
an isolated environment such as .cache/hf-admin-venv.
"""
import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, Volume
from huggingface_hub.utils import disable_progress_bars

ROOT = Path(__file__).resolve().parents[1]


def main(languages, retry_failed=False, timeout_hours=None):
    disable_progress_bars()
    api = HfApi()
    config = json.loads((ROOT / 'deploy/huggingface/search-config.json').read_text())
    annotation = json.loads((ROOT / 'deploy/huggingface/annotations-source.json').read_text())
    catalog = {d['id']: d for d in json.loads((ROOT / 'web/public/data/corpora.json').read_text())['datasets']}
    if any(language not in config['languages'] for language in languages):
        raise ValueError('Unknown build language')
    hardware = next(h for h in api.list_jobs_hardware() if h.name == config['job_hardware'])
    if hardware.unit_label != 'minute':
        raise ValueError('Hardware billing unit changed')
    hourly = hardware.unit_cost_micro_usd * 60 / 1_000_000
    if hourly > config['job_hourly_price_ceiling_usd']:
        raise ValueError('Hardware price exceeds the configured ceiling')
    ledger_path = ROOT / '.cache/corpus-search-jobs.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'jobs': [], 'probe_ceiling_usd': 0.015}
    for language in languages:
        existing = [j for j in ledger['jobs'] if j['language'] == language]
        if existing:
            job = api.inspect_job(job_id=existing[-1]['id'], namespace='V4ldeLund')
            if not retry_failed or str(job.status.stage) not in {'ERROR', 'FAILED', 'CANCELED', 'TIMEOUT'}:
                raise ValueError(f'{language} already has job {job.id} ({job.status.stage})')
    timeout_hours = timeout_hours or config['job_timeout_hours']
    if not 0 < timeout_hours <= config['job_timeout_hours']:
        raise ValueError('Timeout exceeds the configured maximum')
    maximum = hourly * timeout_hours
    reserved = sum(j['maximum_usd'] for j in ledger['jobs']) + ledger['probe_ceiling_usd']
    if reserved + len(languages) * maximum > config['build_budget_usd']:
        raise ValueError('Job reservation would exceed the build budget')
    files = [('scripts/build_corpus_search.py', 'scripts/build_corpus_search.py'),
             ('server/corpus_search.py', 'server/corpus_search.py'),
             ('server/remote_ann.py', 'server/remote_ann.py'),
             ('web/public/data/corpora.json', 'corpora.json'),
             ('deploy/huggingface/search-config.json', 'search-config.json')]
    fingerprint = hashlib.sha256(b''.join((ROOT / name).read_bytes() for name, _ in files)).hexdigest()[:16]
    prefix = f'build/{fingerprint}'
    api.batch_bucket_files(config['bucket'], add=[(ROOT / name, f'{prefix}/{target}') for name, target in files])
    for language in languages:
        data = catalog[language]
        command = ('pip install --no-cache-dir model2vec==' + config['model2vec_version']
                   + ' tantivy==0.26.0 faiss-cpu==1.13.2 pyarrow==23.0.1 PyYAML==6.0.3'
                   + f' && python /data/{prefix}/scripts/build_corpus_search.py {language}'
                   + f' --catalog /data/{prefix}/corpora.json')
        job = api.run_job(image='python:3.11-slim-bookworm', flavor=config['job_hardware'],
                         timeout=f'{timeout_hours}h', attempts=1,
                         name=f'dynaword-{language}-search', labels={'project': 'dynaword', 'language': language},
                         env={'PYTHONUNBUFFERED': '1', 'OMP_NUM_THREADS': '6',
                              'OPENBLAS_NUM_THREADS': '1', 'RAYON_NUM_THREADS': '6'},
                         volumes=[Volume(type='bucket', source=config['bucket'], mount_path='/data'),
                                  Volume(type='model', source=config['model'], revision=config['model_revision'], mount_path='/model', read_only=True),
                                  Volume(type='dataset', source=data['repo'], revision=data['revision'], mount_path='/corpus', read_only=True),
                                  Volume(type='dataset', source=annotation['repo'], revision=annotation['revision'], path='corpus-annotations', mount_path='/annotations', read_only=True)],
                         command=['bash', '-lc', command])
        ledger['jobs'].append({'language': language, 'id': job.id, 'revision': data['revision'],
                               'code': fingerprint, 'maximum_usd': maximum, 'timeout_hours': timeout_hours})
        ledger_path.write_text(json.dumps(ledger, indent=2))
        print(json.dumps(ledger['jobs'][-1]), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('languages', nargs='+')
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--timeout-hours', type=int)
    args = parser.parse_args()
    main(args.languages, args.retry_failed, args.timeout_hours)
