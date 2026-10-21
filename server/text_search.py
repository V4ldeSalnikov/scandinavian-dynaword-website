from functools import lru_cache
from pathlib import Path
import json
import threading

import tantivy

CACHE=Path(__file__).resolve().parents[1]/'.cache'
FIELDS={'source','domain','content_quality','pii_presence','content_type','information_density','educational_value','content_safety','content_integrity','reasoning_indicators'}

EXTRA_FIELDS={'content_ratio','content_length'}
METADATA_LOCK=threading.Lock()


@lru_cache(maxsize=2)
def metadata_clause(raw):
    # These two columns were added after the persisted text-index schema.
    # Intersect document identities inside Tantivy before counts and pagination.
    from server.app import database, parse_filters
    where,params=parse_filters(raw)
    with database() as connection:
        keys=[row[0] for row in connection.execute("SELECT source || '/' || id FROM records WHERE "+where,params).fetchall()]
    return tantivy.Query.const_score_query(tantivy.Query.term_set_query(get_index().schema,'key',keys),0.0)


def status():
    p=CACHE/'search_manifest.json'
    return json.loads(p.read_text()) if p.exists() else {'status':'building','records':0,'sources':[]}


@lru_cache(maxsize=1)
def get_index():
    return tantivy.Index.open(str(CACHE/'fulltext'))


def query_for(index, text, filters):
    parts=[(tantivy.Occur.Must,index.parse_query(text,['text']))]
    if filters.get('topic_id') not in (None, ''):
        from server.topics import text_clause
        parts.append((tantivy.Occur.Must, text_clause(filters['topic_id'])))
    for field in FIELDS:
        if filters.get(field):parts.append((tantivy.Occur.Must,tantivy.Query.term_query(index.schema,field,str(filters[field]))))
    key,value=filters.get('annotation_key'),filters.get('annotation_value')
    extra={field:filters[field] for field in EXTRA_FIELDS if filters.get(field)}
    if key and value:
        if key in EXTRA_FIELDS:extra.update(annotation_key=key,annotation_value=value)
        elif key in FIELDS:parts.append((tantivy.Occur.Must,tantivy.Query.term_query(index.schema,key,str(value))))
        else:raise ValueError('Unknown annotation')
    if extra:
        with METADATA_LOCK:
            clause=metadata_clause(json.dumps(extra,sort_keys=True))
        parts.append((tantivy.Occur.Must,clause))
    low,high=filters.get('min_tokens'),filters.get('max_tokens')
    if low not in ('',None) or high not in ('',None):
        parts.append((tantivy.Occur.Must,tantivy.Query.range_query(index.schema,'token_count',tantivy.FieldType.Unsigned,int(low) if low not in ('',None) else None,int(high) if high not in ('',None) else None)))
    return tantivy.Query.boolean_query(parts)


def search(text, filters, offset=0, limit=30):
    index=get_index();index.reload();searcher=index.searcher()
    query=query_for(index,text,filters)
    results=searcher.search(query,limit=limit,offset=offset,count=True)
    rows=[]
    for score,address in results.hits:
        doc=searcher.doc(address).to_dict()
        source,record_id=doc['key'][0].split('/',1)
        raw=doc['text'][0]
        terms=[word.strip('"').lower() for word in text.split() if len(word)>2]
        positions=[raw.lower().find(term) for term in terms]
        start=max(0,min((p for p in positions if p>=0),default=0)-110)
        rows.append({'source':source,'id':record_id,'preview':('…' if start else '')+raw[start:start+700],'score':score})
    return rows,results.count


def original_text(source,record_id):
    if not (CACHE/'fulltext/meta.json').exists():return None
    return next(original_texts([(source, record_id)]))


def original_texts(keys):
    """Read a batch from one stable index snapshot, avoiding repeated reloads."""
    index=get_index();index.reload();searcher=index.searcher()
    for source,record_id in keys:
        query=tantivy.Query.term_query(index.schema,'key',source+'/'+record_id)
        result=searcher.search(query,limit=1,count=False)
        yield searcher.doc(result.hits[0][1]).to_dict()['text'][0] if result.hits else None
