"""Build a local full-text index over every original document, with stored text.

Resumes source by source. Downloads one source at a time and removes its temporary
Parquet after committing. Annotation-only files are never indexed as text.
"""
from pathlib import Path
import json
import shutil
import time

import duckdb
import requests
import tantivy
import yaml
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.cache'
FIELDS=['source','domain','content_quality','pii_presence','content_type','information_density','educational_value','content_safety','content_integrity','reasoning_indicators']


def main():
    manifest=json.loads((CACHE/'manifest.json').read_text())
    revision=manifest['revision']
    folder=CACHE/'fulltext'
    folder.mkdir(exist_ok=True)
    state_file=CACHE/'search_manifest.json'
    state=json.loads(state_file.read_text()) if state_file.exists() else {'revision':revision,'status':'building','sources':[],'records':0}
    if state['revision']!=revision:
        raise RuntimeError('Search index revision differs from the corpus revision; use a new cache directory.')
    if (folder/'meta.json').exists():
        index=tantivy.Index.open(str(folder))
    else:
        builder=tantivy.SchemaBuilder()
        builder.add_text_field('text',stored=True)
        builder.add_text_field('key',stored=True,tokenizer_name='raw')
        builder.add_unsigned_field('token_count',indexed=True,fast=True)
        for field in FIELDS:
            builder.add_text_field(field,tokenizer_name='raw')
        index=tantivy.Index(builder.build(),path=str(folder))
    writer=index.writer(heap_size=180_000_000,num_threads=2)
    sources=[c['config_name'] for c in yaml.safe_load((CACHE/revision/'README.md').read_text().split('---')[1])['configs'] if c['config_name'] not in ['default','meta']]
    pending=set(sources)-set(state['sources'])
    while pending:
        available=[s for s in pending if (CACHE/revision/f'{s}.parquet').exists()]
        if not available:
            print('Waiting for remaining source metadata…',flush=True)
            time.sleep(10)
            continue
        available.sort(key=lambda s:json.loads((CACHE/revision/f'{s}.json').read_text())['tokens'])
        source=available[0]
        info=json.loads((CACHE/revision/f'{source}.json').read_text())
        if shutil.disk_usage(CACHE).free<8*1024**3:
            raise RuntimeError('Less than 8 GB free: stopping before downloading another source.')
        print(f"Downloading {source} ({info['records']:,} records)…",flush=True)
        raw_file=CACHE/f'download-{source}.parquet'
        url=f'https://huggingface.co/datasets/danish-foundation-models/danish-dynaword/resolve/{revision}/data/{source}/data.parquet'
        prefetch=raw_file.with_suffix('.prefetch')
        if prefetch.exists() and not raw_file.exists():
            print(f'Waiting for the in-progress {source} download…',flush=True)
            last_size=-1;last_progress=time.monotonic();started_wait=last_progress
            while prefetch.exists() and not raw_file.exists():
                try:size=prefetch.stat().st_size
                except FileNotFoundError:break
                if size!=last_size:last_size=size;last_progress=time.monotonic()
                if time.monotonic()-last_progress>90 or time.monotonic()-started_wait>900:break
                time.sleep(2)
        if not raw_file.exists():
            temp=raw_file.with_suffix('.partial')
            for attempt in range(4):
                try:
                    with requests.get(url,stream=True,timeout=(20,90)) as r:
                        r.raise_for_status()
                        with temp.open('wb') as out:
                            for chunk in r.iter_content(4*1024*1024):
                                out.write(chunk)
                    temp.replace(raw_file)
                    break
                except requests.RequestException:
                    if attempt==3: raise
                    time.sleep(3+attempt*3)
        print(f'Indexing {source}…',flush=True)
        writer.delete_documents('source',source)
        c=duckdb.connect()
        c.execute("SET memory_limit='1GB'; SET threads=1; SET preserve_insertion_order=false")
        projection=','.join('m."'+f+'"' for f in FIELDS)
        cursor=c.execute(f'SELECT m.id,m.token_count,{projection} FROM read_parquet(?) m ORDER BY source_row',[str(CACHE/revision/f'{source}.parquet')])
        n=0;t=time.time()
        columns=[d[0] for d in cursor.description]
        for raw_batch in pq.ParquetFile(raw_file).iter_batches(batch_size=32,columns=['id','text']):
            raw_rows=raw_batch.to_pylist()
            batch=cursor.fetchmany(len(raw_rows))
            if len(batch)!=len(raw_rows):raise RuntimeError('Metadata/text batch sizes differ')
            for values,raw in zip(batch,raw_rows):
                row=dict(zip(columns,values))
                if raw['id']!=row['id']:raise RuntimeError(f'{source}: row-order identity mismatch')
                doc={'text':raw['text'],'key':source+'/'+row['id'],'token_count':row['token_count']}
                for field in FIELDS:
                    value=row[field]
                    doc[field]=value if value is not None and value!=[] else '__missing__'
                writer.add_document(tantivy.Document.from_dict(doc,index.schema))
                n+=1
            if n%100096==0:print(f'  {source}: {n:,} records, {time.time()-t:.0f}s',flush=True)
        if n!=info['records']:
            writer.rollback()
            raise RuntimeError(f'{source}: expected {info["records"]}, indexed {n}; join coverage is invalid')
        writer.commit()
        c.close()
        state['sources'].append(source)
        state['records']+=n
        state['status']='building'
        state_file.write_text(json.dumps(state,indent=2))
        pending.remove(source)
        raw_file.unlink()
        print(f"[{len(state['sources'])}/{len(sources)}] {source} committed. {state['records']:,} total records.",flush=True)
    writer.wait_merging_threads()
    index.reload()
    expected=json.loads((CACHE/'manifest.json').read_text())['records']
    actual=index.searcher().num_docs
    if actual!=expected:
        raise RuntimeError(f'Index has {actual} documents; expected {expected}')
    state.update({'status':'ready','records':actual})
    state_file.write_text(json.dumps(state,indent=2))
    print(f'READY: full-text search over all {actual:,} records',flush=True)


if __name__=='__main__':main()
