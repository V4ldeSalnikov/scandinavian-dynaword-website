"""Read-only corpus API. All SQL filters use parameters and an allowlisted schema."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import json
import os
import threading
import time

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import requests
from server import text_search, semantic_search, topics

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
DATASET = 'danish-foundation-models/danish-dynaword'
FIELDS = ['content_quality', 'pii_presence', 'content_type', 'information_density', 'educational_value', 'content_safety', 'content_integrity', 'reasoning_indicators']
LENGTH_BOUNDS = [0, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576, 2097152, 4194304, 8388608, 16777216, 33554432]
app = FastAPI(title='Danish Dynaword explorer', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=[x for x in os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173').split(',') if x], allow_methods=['GET'], allow_headers=['*'])
app.add_middleware(GZipMiddleware, minimum_size=1000)
pool = ThreadPoolExecutor(max_workers=5)
TEXT_CACHE = CACHE / 'texts'
TEXT_CACHE.mkdir(parents=True, exist_ok=True)


def manifest():
    p = CACHE / 'manifest.json'
    return json.loads(p.read_text()) if p.exists() else {'status': 'preparing', 'sources': []}


@app.get('/')
def service_info():
    return {'service': 'Danish Dynaword API', 'website': 'https://v4ldesalnikov.github.io/scandinavian-dynaword-website/', 'docs': '/docs', 'health': '/api/health'}


@contextmanager
def database():
    if manifest()['status'] != 'ready' or not (CACHE / 'corpus.duckdb').exists():
        raise HTTPException(503, 'The complete corpus index is still being prepared. Please retry shortly.')
    c = duckdb.connect(str(CACHE / 'corpus.duckdb'), read_only=True)
    c.execute("SET threads=4; SET memory_limit='3GB'")
    try:
        yield c
    finally:
        c.close()


def dictionaries(cursor):
    names = [col[0] for col in cursor.description]
    return [dict(zip(names, values)) for values in cursor.fetchall()]


def parse_filters(raw):
    try:
        f = json.loads(raw)
    except Exception:
        raise HTTPException(400, 'Invalid filters')
    if not isinstance(f, dict):
        raise HTTPException(400, 'Filters must be an object')
    clauses, values = [], []
    for field in ['source', 'domain', 'content_quality', 'pii_presence']:
        value = f.get(field)
        if value:
            if value == '__missing__':
                clauses.append(f'"{field}" IS NULL')
            else:
                clauses.append(f'"{field}" = ?')
                values.append(str(value))
    for field, operator in [('min_tokens', '>='), ('max_tokens', '<=')]:
        if f.get(field) not in (None, ''):
            try:
                value = int(f[field])
                assert 0 <= value <= 100_000_000
            except (ValueError, TypeError, AssertionError):
                raise HTTPException(400, 'Invalid token range')
            clauses.append(f'token_count {operator} ?')
            values.append(value)
    key, val = f.get('annotation_key'), f.get('annotation_value')
    if key and val:
        if key not in FIELDS:
            raise HTTPException(400, 'Unknown annotation field')
        if key == 'content_type':
            if val == '__missing__':
                clauses.append('(content_type IS NULL OR len(content_type)=0)')
            else:
                clauses.append('list_contains(content_type, ?)')
                values.append(str(val))
        elif val == '__missing__':
            clauses.append(f'"{key}" IS NULL')
        else:
            clauses.append(f'"{key}" = ?')
            values.append(str(val))
    if f.get('topic_id') not in (None, ''):
        topic_id = topics.validate_id(f['topic_id'])
        clauses.append('record_no IN (SELECT record_no FROM read_parquet(?) WHERE topic_id=?)')
        values.extend([topics.assignment_path(), topic_id])
    return ' AND '.join(clauses) or 'TRUE', values


@app.get('/api/health')
def health():
    m = manifest()
    return {'status': m['status'], 'sources_prepared': len(m['sources']), 'errors': m.get('errors', []), 'text_search': text_search.status()}


@app.get('/api/manifest')
def get_manifest():
    m = manifest()
    semantic = semantic_search.status()
    text = text_search.status()
    m['search'] = {'text': text['status']=='ready' and text.get('revision')==m.get('revision'), 'text_index': text, 'semantic': semantic['status']=='ready' and semantic.get('revision')==m.get('revision'), 'semantic_index': semantic}
    return m


@lru_cache(maxsize=96)
def stats_cached(raw, annotation):
    where, params = parse_filters(raw)
    with database() as c:
        totals = dictionaries(c.execute(f'SELECT count(*) AS records, coalesce(sum(token_count),0) AS tokens, count(DISTINCT source) AS sources, count(content_quality) AS annotated FROM records WHERE {where}', params))[0]
        domains = dictionaries(c.execute(f'SELECT domain AS name, count(*) AS records, sum(token_count) AS tokens FROM records WHERE {where} GROUP BY domain ORDER BY tokens DESC', params))
        sources = dictionaries(c.execute(f'SELECT source AS name, domain, count(*) AS records, sum(token_count) AS tokens FROM records WHERE {where} GROUP BY source,domain ORDER BY tokens DESC', params))
        case = 'CASE ' + ' '.join(f'WHEN token_count < {bound} THEN {i}' for i, bound in enumerate(LENGTH_BOUNDS[1:])) + f' ELSE {len(LENGTH_BOUNDS)-2} END'
        hist = dictionaries(c.execute(f'SELECT {case} AS bin, count(*) AS records FROM records WHERE {where} GROUP BY bin ORDER BY bin', params))
        indexed = {r['bin']: r['records'] for r in hist}
        histogram = [{'min': a, 'max': b-1, 'records': indexed.get(i, 0)} for i, (a, b) in enumerate(zip(LENGTH_BOUNDS, LENGTH_BOUNDS[1:]))]
        if annotation == 'content_type':
            annotations = dictionaries(c.execute(f"SELECT name,count(*) AS records FROM (SELECT unnest(CASE WHEN content_type IS NULL OR len(content_type)=0 THEN ['__missing__'] ELSE list_distinct(content_type) END) AS name FROM records WHERE {where}) GROUP BY name ORDER BY records DESC", params))
            covered = c.execute(f'SELECT count(*) FROM records WHERE {where} AND content_type IS NOT NULL AND len(content_type)>0', params).fetchone()[0]
        else:
            annotations = dictionaries(c.execute(f'SELECT coalesce("{annotation}", \'__missing__\') AS name, count(*) AS records FROM records WHERE {where} GROUP BY name ORDER BY records DESC', params))
            covered = c.execute(f'SELECT count("{annotation}") FROM records WHERE {where}', params).fetchone()[0]
        return {'totals': totals, 'domains': domains, 'sources': sources, 'histogram': histogram, 'annotations': annotations, 'annotation_covered': covered, 'annotation': annotation}


@app.get('/api/stats')
def stats(filters: str = '{}', annotation: str = 'content_quality'):
    if annotation not in FIELDS:
        raise HTTPException(400, 'Unknown annotation field')
    return stats_cached(filters, annotation)


@app.get('/api/topics')
def topic_manifest():
    return topics.status()


@app.get('/api/topics/view')
def topic_view(filters: str = '{}'):
    return topics.view_cached(filters)


ROW_COLUMNS = 'record_no,id,source,domain,token_count,added,created,source_row,one_sentence_description,content_quality,pii_presence,content_type'


@app.get('/api/rows')
def rows(filters: str = '{}', offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), sort: str = 'original'):
    where, params = parse_filters(filters)
    order = {'original': 'record_no', 'shortest': 'token_count,record_no', 'longest': 'token_count DESC,record_no'}.get(sort)
    if not order:
        raise HTTPException(400, 'Unknown sort order')
    with database() as c:
        data = dictionaries(c.execute(f'SELECT {ROW_COLUMNS} FROM records WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?', params + [limit + 1, offset]))
    return {'rows': data[:limit], 'has_more': len(data) > limit, 'next_offset': offset + limit}


def hf_request(endpoint, params):
    for attempt in range(4):
        try:
            r = requests.get('https://datasets-server.huggingface.co/' + endpoint, params={'dataset': DATASET, 'split': 'train', **params}, timeout=45)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(1 + attempt * 2)
                continue
            r.raise_for_status()
            if r.headers.get('x-revision') != manifest()['revision']:
                raise HTTPException(409, 'The upstream dataset revision changed. Refresh the local index before using live search.')
            return r.json()
        except requests.RequestException:
            if attempt == 3:
                raise HTTPException(502, 'Hugging Face is temporarily unable to serve this query. Please retry.')
    raise HTTPException(502, 'Dataset service unavailable')


def record_metadata(record_no):
    with database() as c:
        found = dictionaries(c.execute('SELECT * FROM records WHERE record_no=?', [record_no]))
    if not found:
        raise HTTPException(404, 'Record not found')
    return found[0]


def load_text(row, complete=False):
    m = manifest()
    local = text_search.original_text(row['source'],row['id']) if text_search.status().get('revision') == m['revision'] else None
    if local is not None:
        return {'text':local,'truncated':False}
    filename = TEXT_CACHE / f"{m['revision']}-{row['record_no']}.json"
    if filename.exists():
        stored = json.loads(filename.read_text())
        if not complete or not stored['truncated']:
            return stored
    else:
        stored = None
    if not complete:
        result = hf_request('rows', {'config': row['source'], 'offset': row['source_row'], 'length': 1})
        if result['rows'] and result['rows'][0]['row']['id'] == row['id']:
            raw = result['rows'][0]
            stored = {'text': raw['row']['text'], 'truncated': 'text' in raw.get('truncated_cells', [])}
        else:
            complete = True
    if complete:
        url = f"https://huggingface.co/datasets/{DATASET}/resolve/{m['revision']}/data/{row['source']}/data.parquet"
        c = duckdb.connect()
        try:
            raw = c.execute('SELECT id,text FROM read_parquet(?, file_row_number=true) WHERE file_row_number=?', [url, row['source_row']]).fetchone()
        finally:
            c.close()
        if not raw or raw[0] != row['id']:
            raise HTTPException(409, 'The record identity did not match the pinned source file.')
        stored = {'text': raw[1], 'truncated': False}
    temp = filename.with_suffix(f'.{threading.get_ident()}.tmp')
    temp.write_text(json.dumps(stored))
    temp.replace(filename)
    return stored


@app.get('/api/record/{record_no}')
def record(record_no: int, offset: int = Query(0, ge=0), limit: int = Query(16000, ge=1, le=100000), complete: bool = False):
    row = record_metadata(record_no)
    stored = load_text(row, complete or offset > 0)
    chunk = stored['text'][offset:offset+limit]
    return {'record': row, 'text': chunk, 'text_length': len(stored['text']), 'offset': offset, 'next_offset': offset+len(chunk), 'has_more': len(stored['text']) > offset+limit or stored['truncated'], 'upstream_truncated': stored['truncated']}


@app.get('/api/previews')
def previews(ids: str):
    try:
        record_ids = [int(x) for x in ids.split(',')][:30]
    except ValueError:
        raise HTTPException(400, 'Invalid record IDs')
    def preview(record_id):
        try:
            r = load_text(record_metadata(record_id))
            return str(record_id), {'text': r['text'][:700]}
        except Exception:
            return str(record_id), {'unavailable': True}
    return dict(pool.map(preview, record_ids))


@app.get('/api/search')
def search(q: str = Query(..., min_length=2, max_length=250), filters: str = '{}', cursor: int = Query(0, ge=0), mode: str = 'text'):
    where, params = parse_filters(filters)
    f = json.loads(filters)
    if mode == 'semantic':
        state = semantic_search.status()
        if state['status'] != 'ready' or state.get('revision') != manifest()['revision']:
            raise HTTPException(503, 'The complete semantic index is still being prepared.')
        try:
            ranked, compared = semantic_search.search_cached(q, filters)
        except ValueError as error:
            raise HTTPException(400, str(error))
        matches = ranked[cursor:cursor+30]
        with database() as c:
            found = dictionaries(c.execute(f'SELECT {ROW_COLUMNS} FROM records WHERE record_no IN (SELECT unnest(?))', [[r['record_no'] for r in matches]])) if matches else []
        lookup = {r['record_no']: r for r in found}
        return {'rows': [{**lookup[r['record_no']], 'score': r['score']} for r in matches], 'next_offset': cursor+len(matches), 'has_more': cursor+len(matches)<len(ranked), 'upstream_matches': len(ranked), 'compared': compared, 'mode': mode}
    if mode != 'text':
        raise HTTPException(400, 'Unknown search mode')
    text_state = text_search.status()
    if text_state['status']!='ready' or text_state.get('revision') != manifest()['revision']:
        raise HTTPException(503, 'The complete local text index is still being built. Browsing and annotation filters remain available.')
    try:
        matches,total=text_search.search(q,f,cursor)
    except ValueError:
        raise HTTPException(400, 'The text query could not be parsed. Try simple words or a quoted phrase.')
    if not matches:
        return {'rows':[],'next_offset':cursor,'has_more':False,'upstream_matches':total,'mode':'text'}
    with database() as c:
        conditions=' OR '.join('(source=? AND id=?)' for _ in matches)
        keys=[value for r in matches for value in [r['source'],r['id']]]
        found=dictionaries(c.execute(f'SELECT {ROW_COLUMNS} FROM records WHERE ({where}) AND ({conditions})',params+keys))
    lookup={(r['source'],r['id']):r for r in found}
    output=[]
    for match in matches:
        row=lookup.get((match['source'],match['id']))
        if row:output.append({**row,'preview':match['preview'],'score':match['score']})
    return {'rows':output,'next_offset':cursor+len(matches),'has_more':cursor+len(matches)<total,'upstream_matches':total,'mode':'text'}
