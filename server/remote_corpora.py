"""Revision-checked, paginated access to the complete published Nordic corpora.

Annotation filters scan the complete compact local index. Text and annotations
are joined only after checking the document ID and source identity.
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
from pathlib import Path
import time

import requests
from fastapi import APIRouter, HTTPException, Query
from . import annotation_index, corpus_search, corpus_stats

router = APIRouter(prefix='/api/corpora')
ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'content_quality', 'pii_presence', 'content_integrity', 'content_ratio', 'content_length', 'information_density', 'educational_value', 'reasoning_indicators', 'content_safety'}
POOL = ThreadPoolExecutor(max_workers=6)


@lru_cache(maxsize=1)
def catalog():
    path = ROOT / 'corpora.json'
    if not path.exists():
        path = ROOT / 'web/public/data/corpora.json'
    return {d['id']: d for d in json.loads(path.read_text())['datasets']}


def corpus(language):
    if language not in {'norwegian', 'swedish', 'icelandic', 'faroese'}:
        raise HTTPException(404, 'Unknown corpus')
    return catalog()[language]


@lru_cache(maxsize=16)
def hub_cached(language, endpoint, params_json):
    data = corpus(language)
    params = {'dataset': data['repo'], 'split': 'train', **json.loads(params_json)}
    for attempt in range(2):
        try:
            r = requests.get('https://datasets-server.huggingface.co/'+endpoint, params=params, timeout=(5, 20))
        except requests.RequestException:
            if not attempt:
                continue
            raise HTTPException(503, 'The dataset service is taking longer than usual. Please retry.')
        if r.status_code in {429, 500, 502, 503, 504}:
            if not attempt:
                time.sleep(1)
                continue
            raise HTTPException(503, 'The dataset service is loading this index. Please retry shortly; browsing without search or filters may already be available.')
        if not r.ok:
            raise HTTPException(502, 'The dataset service could not run this query.')
        if r.headers.get('x-revision') != data['revision']:
            raise HTTPException(409, 'This published dataset has changed. Its explorer catalog needs refreshing before these records can be shown.')
        body = r.json()
        if body.get('partial'):
            raise HTTPException(503, 'The upstream index is incomplete for this query. Browse records or choose a smaller source; partial results are not shown as a complete search.')
        return body


def hub(language, endpoint, **params):
    return hub_cached(language, endpoint, json.dumps(params, sort_keys=True))


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def filters_for(data, raw):
    try:
        filters = json.loads(raw)
        if not isinstance(filters, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, 'Invalid filters')
    source = filters.get('source', '')
    domain = filters.get('domain', '')
    sources = [s for s in data['sources'] if (not source or s['id'] == source) and (not domain or s['domain'] == domain)]
    if source and not any(s['id'] == source for s in data['sources']):
        raise HTTPException(400, 'Unknown source')
    annotations = filters.get('annotations', {})
    if not isinstance(annotations, dict) or any(k not in FIELDS for k in annotations):
        raise HTTPException(400, 'Unknown annotation field')
    for key, val in annotations.items():
        if not isinstance(val, str) or not (key in (data.get('annotation_distributions') or {}) and (val == '__missing__' or val in data['annotation_distributions'][key])):
            raise HTTPException(400, 'Unknown annotation value')
    bounds = {}
    for key in ['min_tokens', 'max_tokens']:
        if filters.get(key) not in (None, ''):
            try:
                value = int(filters[key])
                if not 0 <= value <= 100_000_000:
                    raise ValueError()
                bounds[key] = value
            except (ValueError, TypeError):
                raise HTTPException(400, 'Invalid token range')
    return sources, annotations, bounds


def source_offsets(data):
    offset = 0
    result = {}
    for source in sorted(data['sources'], key=lambda s:s['id']):
        result[source['id']] = offset
        offset += source['records']
    return result


def range_groups(positions):
    """Coalesce neighbouring rows while keeping each response small."""
    groups = []
    for pos in sorted(set(positions)):
        if groups and pos == groups[-1][-1]+1 and len(groups[-1]) < 30:
            groups[-1].append(pos)
        else:
            groups.append([pos])
    return groups


def fetch_positions(language, config, positions):
    def fetch(group):
        result = hub(language, 'rows', config=config, offset=group[0], length=len(group))
        return result['rows']
    return {row['row_idx']:row for group in POOL.map(fetch, range_groups(positions)) for row in group}


def join_annotations(language, entries, global_positions, supplied=None):
    data = corpus(language)
    try:
        metadata = supplied if supplied is not None else (fetch_positions(language, 'meta', global_positions) if data.get('annotation_distributions') else {})
    except HTTPException as error:
        if error.status_code == 409:
            raise
        metadata = {}
    index = annotation_index.load(language, data['revision'])
    by_source = {s['id']:s for s in data['sources']}
    output = []
    for raw, pos in zip(entries, global_positions):
        row = raw['row']; candidate = metadata.get(pos, {}).get('row', {})
        source = raw.get('_source') or row.get('source')
        # Compare IDs, and where a source is known also its identity, before joining.
        matched = candidate.get('id') == row['id'] and candidate.get('dataset') == source
        annotations = {k:v for k,v in candidate.items() if k not in {'id','dataset'}} if matched else {}
        if index is not None and 0 <= pos < index[0]['records']:
            indexed_source, _ = annotation_index.location(index, pos)
            if indexed_source == source:
                try:
                    annotations.update(annotation_index.annotations_at(index, pos, row['id']))
                    matched = True
                except ValueError:
                    pass
        text = row.get('text', '')
        output.append({**row, **annotations, 'source':source, 'domain':by_source.get(source, {}).get('domain', ''),
                       'record_no':pos, 'row_index':raw['row_idx'], 'config':raw.get('_config', 'default'),
                       'preview':text[:700], 'text':None, 'annotations_available':matched,
                       'text_truncated':'text' in raw.get('truncated_cells', [])})
    return output


@router.get('/{language}/rows')
def rows(language: str, filters: str = '{}', offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=30)):
    data = corpus(language)
    sources, annotations, bounds = filters_for(data, filters)
    if not sources:
        return {'rows':[], 'has_more':False, 'next_offset':offset, 'total':0}
    allowed = {s['id'] for s in sources}
    if corpus_search.status(data)['text']:
        return corpus_search.text_search(data, '', allowed, annotations, bounds, offset, limit)
    restricted = len(sources) != len(data['sources'])
    # Browsing can use row slicing directly, even for corpora larger than the
    # Hub's query index. Domain browsing walks complete source configurations.
    if not annotations and not bounds:
        if not restricted:
            result = hub(language, 'rows', config='default', offset=offset, length=limit)
            entries = result['rows']; positions=[r['row_idx'] for r in entries]
            total = data['records']
        else:
            offsets = source_offsets(data); remaining=offset; entries=[];positions=[]
            total = sum(s['records'] for s in sources)
            for source in sorted(sources,key=lambda s:s['id']):
                if remaining >= source['records']:
                    remaining -= source['records'];continue
                result=hub(language,'rows',config=source['id'],offset=remaining,length=min(limit-len(entries),source['records']-remaining))
                for raw in result['rows']:
                    entries.append({**raw,'_config':source['id'],'_source':source['id']});positions.append(offsets[source['id']]+raw['row_idx'])
                remaining=0
                if len(entries)>=limit:break
        joined=join_annotations(language,entries,positions)
        return {'rows':joined,'has_more':offset+len(joined)<total,'next_offset':offset+len(joined),'total':total}
    index = annotation_index.load(language, data['revision'])
    if index is not None:
        positions, total = annotation_index.select(index, allowed, annotations, bounds, offset, limit)
        grouped = {}
        for position in positions:
            source, row_index = annotation_index.location(index, position)
            grouped.setdefault(source, []).append((position, row_index))
        by_position = {}
        for source, locations in grouped.items():
            originals = fetch_positions(language, source, [r for _, r in locations])
            for position, row_index in locations:
                raw = originals.get(row_index)
                if raw is None:
                    raise HTTPException(502, 'The dataset service omitted a requested record.')
                try:
                    labels = annotation_index.annotations_at(index, position, raw['row']['id'])
                except ValueError:
                    raise HTTPException(409, 'Text and annotation record identities differ.')
                original = {**raw, '_source':source, '_config':source}
                joined = join_annotations(language, [original], [position], supplied={})[0]
                by_position[position] = {**joined, **labels, 'annotations_available':True}
        output = [by_position[position] for position in positions]
        return {'rows':output, 'has_more':offset+len(output)<total, 'next_offset':offset+len(output), 'total':total}
    raise HTTPException(503, 'Annotation filters are being prepared for this release. Source and domain browsing are available.')


@router.get('/{language}/stats')
def stats(language: str, filters: str = '{}', annotation: str = 'content_quality'):
    data = corpus(language)
    if annotation not in FIELDS:
        raise HTTPException(400, 'Unknown annotation field')
    sources, annotations, bounds = filters_for(data, filters)
    try:
        return corpus_stats.cached(language, data['revision'], json.dumps(sorted(s['id'] for s in sources)),
                                   json.dumps(annotations, sort_keys=True), json.dumps(bounds, sort_keys=True),
                                   annotation, corpus_search.status(data)['text'])
    except ValueError as error:
        raise HTTPException(503, str(error))


@router.get('/{language}/search-status')
def search_status(language: str):
    return corpus_search.status(corpus(language))


@router.get('/{language}/search')
def search(language: str, q: str = Query(..., min_length=2, max_length=1000), mode: str = 'text',
           filters: str = '{}', offset: int = Query(0, ge=0, le=10_000), limit: int = Query(30, ge=1, le=30)):
    data = corpus(language)
    if mode not in {'text', 'semantic'}:
        raise HTTPException(400, 'Unknown search mode')
    if not corpus_search.status(data)[mode]:
        raise HTTPException(503, 'The complete search index is still being prepared for this language.')
    sources, annotations, bounds = filters_for(data, filters)
    if not sources:
        return {'rows': [], 'total': 0, 'has_more': False, 'next_offset': offset}
    try:
        implementation = corpus_search.semantic_search if mode == 'semantic' else corpus_search.text_search
        return implementation(data, q, {s['id'] for s in sources}, annotations, bounds, offset, limit)
    except ValueError as error:
        raise HTTPException(400, str(error))


@router.get('/{language}/record')
def record(language: str, config: str = 'default', row_index: int = Query(...,ge=0), id: str = Query(...,max_length=1000)):
    data=corpus(language)
    if config!='default' and config not in {s['id'] for s in data['sources']}:
        raise HTTPException(400,'Unknown source')
    if corpus_search.status(data)['text']:
        if config == 'default':
            entries = sorted(data['sources'], key=lambda s: s['id'])
            for source in entries:
                if row_index < source['records']:
                    config = source['id']; break
                row_index -= source['records']
        try:
            return corpus_search.original(data, config, row_index, id)
        except ValueError as error:
            raise HTTPException(409, str(error))
    result=hub(language,'rows',config=config,offset=row_index,length=1)
    if not result['rows'] or result['rows'][0]['row']['id']!=id:
        raise HTTPException(409,'The record identity does not match this release.')
    raw=result['rows'][0]
    return {'text':raw['row'].get('text',''),'truncated':'text' in raw.get('truncated_cells',[])}
