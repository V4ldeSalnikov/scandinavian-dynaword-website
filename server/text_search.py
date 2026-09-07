from functools import lru_cache
from pathlib import Path
import json

import tantivy

CACHE=Path(__file__).resolve().parents[1]/'.cache'
FIELDS={'source','domain','content_quality','pii_presence','content_type','information_density','educational_value','content_safety','content_integrity','reasoning_indicators'}


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
    for field in ['source','domain','content_quality','pii_presence']:
        if filters.get(field):parts.append((tantivy.Occur.Must,tantivy.Query.term_query(index.schema,field,str(filters[field]))))
    key,value=filters.get('annotation_key'),filters.get('annotation_value')
    if key and value:
        if key not in FIELDS:raise ValueError('Unknown annotation')
        parts.append((tantivy.Occur.Must,tantivy.Query.term_query(index.schema,key,str(value))))
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
