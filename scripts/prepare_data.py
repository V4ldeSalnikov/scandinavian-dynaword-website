"""Build a complete, revision-pinned metadata index without downloading all text.

Run from the repository root: python3 scripts/prepare_data.py
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import re
import time

import duckdb
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
DATASET = 'danish-foundation-models/danish-dynaword'
ANNOTATIONS = {
    'content_integrity': 'VARCHAR', 'content_ratio': 'VARCHAR',
    'content_length': 'VARCHAR', 'one_sentence_description': 'VARCHAR',
    'content_type': 'VARCHAR[]', 'business_sector': 'VARCHAR[]',
    'technical_content': 'VARCHAR[]', 'information_density': 'VARCHAR',
    'content_quality': 'VARCHAR', 'audience_level': 'VARCHAR',
    'commercial_bias': 'VARCHAR', 'time_sensitivity': 'VARCHAR',
    'content_safety': 'VARCHAR', 'educational_value': 'VARCHAR',
    'reasoning_indicators': 'VARCHAR', 'pii_presence': 'VARCHAR',
    'regional_relevance': 'VARCHAR[]', 'country_relevance': 'VARCHAR[]',
}


def get(url):
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(1 + attempt * 2)


def clean_markdown(text):
    text = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', text)
    return re.sub(r'\[([^]]+)\]', r'\1', text).strip()


def parquet_url(url):
    # Resolve once so each Parquet range request goes directly to file storage.
    # Temporary signed URLs stay in memory and are never saved in the manifest.
    response = requests.head(url, allow_redirects=True, timeout=90)
    response.raise_for_status()
    return response.url


def download_file(url, destination):
    if destination.exists():
        return str(destination)
    temporary=destination.with_suffix('.partial')
    with requests.get(url,stream=True,timeout=(20,90)) as response:
        response.raise_for_status()
        with temporary.open('wb') as out:
            for chunk in response.iter_content(4*1024*1024):out.write(chunk)
    temporary.replace(destination)
    return str(destination)


def prepare(revision=None, workers=4):
    CACHE.mkdir(exist_ok=True)
    previous = CACHE / 'manifest.json'
    revision = revision or (json.loads(previous.read_text())['revision'] if previous.exists() else get(f'https://huggingface.co/api/datasets/{DATASET}').json()['sha'])
    if previous.exists():
        saved = json.loads(previous.read_text())
        if saved['revision'] != revision:
            raise RuntimeError('Move the existing .cache directory aside before importing a different revision, so text and vector indexes cannot be mixed.')
        if saved['revision'] == revision and saved['status'] == 'ready' and (CACHE/'corpus.duckdb').exists():
            print(f"Already ready: {saved['records']:,} records at {revision}")
            return
    target = CACHE / revision
    target.mkdir(exist_ok=True)
    base = f'https://huggingface.co/datasets/{DATASET}/resolve/{revision}/'
    card = get(base + 'README.md').text
    (target / 'README.md').write_text(card)
    front = yaml.safe_load(card.split('---')[1])
    sources = sorted(c['config_name'] for c in front['configs'] if c['config_name'] not in ('default', 'meta'))
    descriptions = {}
    for line in card.splitlines():
        cols = [c.strip() for c in line.strip('|').split('|')]
        if len(cols) == 5 and re.fullmatch(r'\[[\w-]+\]', cols[0]):
            descriptions[cols[0][1:-1]] = {'description': clean_markdown(cols[1]), 'domain': cols[2], 'license': clean_markdown(cols[4])}
    manifest = {'dataset': DATASET, 'revision': revision, 'sources': [], 'status': 'preparing', 'errors': [], 'published_stats': get(base + 'descriptive_stats.json').json()}
    previous.write_text(json.dumps(manifest, indent=2))

    def one(source):
        local = target / f'{source}.parquet'
        info_file = target / f'{source}.json'
        if local.exists() and info_file.exists():
            return json.loads(info_file.read_text())
        info = {'id': source, 'name': source.replace('_', ' ').replace('-', ' '), **descriptions.get(source, {}), 'url': f'https://huggingface.co/datasets/{DATASET}/blob/{revision}/data/{source}/{source}.md'}
        try:
            doc = get(base + f'data/{source}/{source}.md').text
            header = yaml.safe_load(doc.split('---')[1]) if doc.startswith('---') else {}
            info['name'] = header.get('pretty_name', info['name'])
            info.setdefault('domain', (header.get('domains') or ['Other'])[0])
            info.setdefault('license', header.get('license_name', header.get('license', 'See source')))
        except Exception:
            info.setdefault('domain', 'Other')
            info.setdefault('license', 'See source')
        info.setdefault('description', '')
        conn = duckdb.connect()
        conn.execute("SET threads=2; SET memory_limit='1GB'; SET enable_progress_bar=false; SET allow_asterisks_in_http_paths=true")
        data_url=base + f'data/{source}/data.parquet'
        # The newspaper source has many small row groups; a single sequential
        # transfer is much faster than thousands of individual HTTP ranges.
        if source=='enevaeldens_nyheder':
            print(f'Downloading complete {source} file for efficient indexing…',flush=True)
            data_url=download_file(data_url,CACHE/f'download-{source}.parquet')
        else:
            data_url=parquet_url(data_url)
        conn.execute('CREATE TEMP TABLE texts AS SELECT id, source AS original_source, token_count, added, created, file_row_number AS source_row FROM read_parquet(?, file_row_number=true)', [data_url])
        count = conn.execute('SELECT count(*) FROM texts').fetchone()[0]
        try:
            meta_url = base + f'data/{source}/metadata.parquet'
            meta_path=target/f'{source}.metadata.parquet'
            conn.execute('CREATE TEMP TABLE annotations AS SELECT * FROM read_parquet(?)', [download_file(meta_url,meta_path)])
            duplicates = conn.execute('SELECT count(*) FROM (SELECT id FROM annotations GROUP BY id HAVING count(*) > 1)').fetchone()[0]
            if duplicates:
                raise ValueError(f'{source}: duplicate annotation IDs: {duplicates}')
        except (duckdb.HTTPException, requests.HTTPError) as error:
            if '404' not in str(error):
                raise
            schema = ', '.join(f'"{k}" {v}' for k, v in ANNOTATIONS.items())
            conn.execute(f'CREATE TEMP TABLE annotations (id VARCHAR, {schema})')
        columns = ', '.join('a."' + key + '"' for key in ANNOTATIONS)
        conn.execute(f'CREATE TEMP TABLE joined AS SELECT ?::VARCHAR AS source, ?::VARCHAR AS domain, t.*, {columns} FROM texts t LEFT JOIN annotations a ON t.id=a.id', [source, info['domain']])
        actual = conn.execute('SELECT count(*), sum(token_count), count(content_quality) FROM joined').fetchone()
        if actual[0] != count:
            raise ValueError(f'{source}: join changed row count')
        info.update({'records': count, 'tokens': actual[1] or 0, 'annotated': actual[2]})
        conn.execute('COPY joined TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(local)])
        conn.close()
        info_file.write_text(json.dumps(info, indent=2))
        return info

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, s): s for s in sources}
        for fut in as_completed(futures):
            source = futures[fut]
            try:
                info = fut.result()
                manifest['sources'].append(info)
                print(f"[{len(manifest['sources'])}/{len(sources)}] {source}: {info['records']:,} records", flush=True)
            except Exception as e:
                message = re.sub(r'https://[^\s\']+', '<remote parquet>', str(e))
                manifest['errors'].append({'source': source, 'error': message})
                print(f'ERROR {source}: {message}', flush=True)
            previous.write_text(json.dumps(manifest, indent=2))
    if manifest['errors']:
        raise RuntimeError('Some sources failed. Re-run to resume; no partial corpus will be marked complete.')

    print('Assembling full-corpus index…', flush=True)
    db_file = CACHE / 'corpus.building.duckdb'
    if db_file.exists():
        db_file.unlink()
    conn = duckdb.connect(str(db_file))
    conn.execute("SET threads=4; SET memory_limit='4GB'")
    files = [str(target / f'{s}.parquet') for s in sources]
    conn.execute('CREATE TABLE records AS SELECT row_number() OVER () - 1 AS record_no, * FROM read_parquet(?, union_by_name=true)', [files])
    actual = conn.execute('SELECT count(*), sum(token_count), count(content_quality) FROM records').fetchone()
    manifest.update({'records': actual[0], 'tokens': actual[1], 'annotated': actual[2], 'status': 'ready'})
    expected = manifest['published_stats']['number_of_samples']
    if actual[0] != expected:
        raise RuntimeError(f'Expected {expected} records; found {actual[0]}. Investigate before serving.')
    conn.execute('CREATE UNIQUE INDEX record_no_idx ON records(record_no)')
    conn.execute('CHECKPOINT')
    conn.close()
    db_file.replace(CACHE / 'corpus.duckdb')
    manifest['sources'].sort(key=lambda s: -s['records'])
    previous.write_text(json.dumps(manifest, indent=2))
    print(f"READY: {actual[0]:,} records, {actual[1]:,} tokens, {actual[2]:,} annotated", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    prepare(args.revision, args.workers)
