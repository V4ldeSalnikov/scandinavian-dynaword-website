"""Revision-bound Turftopic sidecars; corpus counts are never sampled."""
from functools import lru_cache
import json
import threading

from fastapi import HTTPException
import tantivy

TERM_LOCK = threading.Lock()


def status():
    from server.app import CACHE, manifest
    path = CACHE/'topics_manifest.json'
    if not path.exists():
        return {'status': 'unavailable'}
    result = json.loads(path.read_text())
    semantic_path = CACHE/'semantic_manifest.json'
    semantic = json.loads(semantic_path.read_text()) if semantic_path.exists() else {}
    if result.get('revision') != manifest().get('revision') or result.get('metadata_fingerprint') != semantic.get('metadata_fingerprint'):
        return {'status': 'stale'}
    return result


def require_ready():
    state = status()
    if state['status'] != 'ready':
        raise HTTPException(503, 'The topic model is not available for this corpus revision yet.')
    return state


def assignment_path():
    from server.app import CACHE
    require_ready()
    return str(CACHE/'topics/assignments.parquet')


def validate_id(value):
    state = require_ready()
    try:
        if isinstance(value, bool) or str(int(value)) != str(value):
            raise ValueError()
        topic_id = int(value)
        if topic_id not in {-1, *(t['id'] for t in state['topics'])}:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(400, 'Unknown topic')
    return topic_id


@lru_cache(maxsize=16)
def view_cached(raw):
    from server.app import CACHE, database, dictionaries, parse_filters
    state = require_ready()
    where, params = parse_filters(raw)
    base_filters = json.loads(raw)
    base_filters.pop('topic_id', None)
    base_where, base_params = parse_filters(json.dumps(base_filters))
    path = assignment_path()
    with database() as c:
        # Apply all metadata filters before the topic join. Explicit projection
        # avoids ambiguous record_no references in nested topic-filter queries.
        distributions = dictionaries(c.execute(f'''SELECT topic_id,count(*) AS records,sum(token_count) AS tokens
            FROM (SELECT record_no,token_count FROM records WHERE {base_where}) r
            JOIN read_parquet(?) t USING(record_no) GROUP BY topic_id ORDER BY records DESC''', base_params+[path]))
        points = c.execute(f'''SELECT p.record_no,p.x,p.y,t.topic_id,r.source,r.domain,
                r.content_quality,r.pii_presence,p.preview
            FROM (SELECT record_no,source,domain,content_quality,pii_presence FROM records WHERE {where}) r
            JOIN read_parquet(?) p USING(record_no)
            JOIN read_parquet(?) t USING(record_no) ORDER BY p.record_no''', params+[str(CACHE/'topics/points.parquet'), path]).fetchall()
        selected = c.execute(f'SELECT count(*) FROM records WHERE {where}', params).fetchone()[0]
    return {'revision': state['revision'], 'distributions': distributions, 'points': points,
            'selected_records': selected, 'base_records': sum(d['records'] for d in distributions)}


@lru_cache(maxsize=1)
def _topic_term_query(topic_id, cache_key):
    from server.app import database
    from server.text_search import get_index
    # Intersect inside Tantivy so match counts and pagination are exact. A
    # post-filter over a page of text hits would silently lose matching records.
    with database() as c:
        keys = [r[0] for r in c.execute("SELECT source || '/' || id FROM records WHERE record_no IN (SELECT record_no FROM read_parquet(?) WHERE topic_id=?)", [assignment_path(), topic_id]).fetchall()]
    return tantivy.Query.const_score_query(tantivy.Query.term_set_query(get_index().schema, 'key', keys), 0.0)


def text_clause(topic_id):
    from server.app import CACHE
    state = require_ready()
    topic_id = validate_id(topic_id)
    with TERM_LOCK:
        return _topic_term_query(topic_id, (str(CACHE), state['metadata_fingerprint']))
