"""Build full annotation/length indexes for the additional annotated corpora.

Join annotations to originals by ID. Save compact codes, token counts and ID
checksums in original file order, so text retrieval can verify each identity.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib,json
from pathlib import Path

import duckdb
import numpy as np
import requests
from huggingface_hub import hf_hub_download
from huggingface_hub.errors import EntryNotFoundError

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.cache/corpus-annotations'
FIELDS=['content_quality','pii_presence','content_integrity','content_ratio','content_length','information_density','educational_value','reasoning_indicators','content_safety']
DTYPE=np.dtype([('id_hash','<u8'),('tokens','<u4')]+[(f,'u1') for f in FIELDS])


def identity_hash(identifier):
    return int.from_bytes(hashlib.blake2b(identifier.encode('utf-8'),digest_size=8).digest(),'little')


def url(repo,revision,path):
    r=requests.head(f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{path}',allow_redirects=True,timeout=90)
    r.raise_for_status();return r.url


def build(prepare_only=None):
    OUT.mkdir(exist_ok=True)
    catalog=json.loads((ROOT/'web/public/data/corpora.json').read_text())
    result={'version':1,'fields':FIELDS,'languages':{}}
    for d in catalog['datasets']:
        if d['id'] not in {'norwegian','icelandic','faroese'}:continue
        if prepare_only and d['id'] != prepare_only:continue
        labels={f:{v:i+1 for i,v in enumerate((d['annotation_distributions'] or {}).get(f,{}))} for f in FIELDS}
        folder=OUT/'prepared'/d['id']/d['revision'];folder.mkdir(parents=True,exist_ok=True)
        def prepare(s):
            dest=folder/(s['id']+'.npy')
            if dest.exists():return
            conn=duckdb.connect()
            conn.execute("SET allow_asterisks_in_http_paths=true; SET threads=4; SET memory_limit='3GB'; SET preserve_insertion_order=true; SET enable_progress_bar=false")
            temp=folder/'tmp'/s['id'];temp.mkdir(parents=True,exist_ok=True)
            conn.execute('SET temp_directory=?',[str(temp)])
            def source_file(filename):
                path=f"data/{s['id']}/{filename}"
                if s['records'] > 5_000_000:
                    return hf_hub_download(d['repo'],path,repo_type='dataset',revision=d['revision'],local_dir=OUT/'raw'/d['revision'])
                return url(d['repo'],d['revision'],path)
            data=source_file('data.parquet')
            try:meta=source_file('metadata.parquet')
            except (requests.HTTPError, EntryNotFoundError) as e:
                if e.response.status_code!=404:raise
                meta=None
            columns=[]
            for field in FIELDS:
                cases=' '.join("WHEN '"+v.replace("'","''")+f"' THEN {code}" for v,code in labels[field].items())
                columns.append(f"(CASE WHEN m.\"{field}\" IS NULL THEN 0 ELSE CASE m.\"{field}\" {cases} ELSE 255 END END)::UTINYINT AS \"{field}\"" if meta else f'0::UTINYINT AS "{field}"')
            query='SELECT t.id,t.token_count::UINTEGER AS tokens,'+','.join(columns)+' FROM read_parquet(?,file_row_number=true) t'
            args=[data]
            if meta:query+=' LEFT JOIN read_parquet(?) m ON t.id=m.id';args.append(meta)
            query+=' ORDER BY t.file_row_number'
            reader=conn.execute(query,args).to_arrow_reader(32768)
            partial=dest.with_suffix('.partial.npy');arr=np.lib.format.open_memmap(partial,mode='w+',dtype=DTYPE,shape=(s['records'],));pos=0
            for batch in reader:
                n=batch.num_rows
                if pos+n>len(arr):raise ValueError(f"Join inflated records: {d['id']}/{s['id']}")
                arr['id_hash'][pos:pos+n]=[identity_hash(v) for v in batch.column('id').to_pylist()]
                arr['tokens'][pos:pos+n]=batch.column('tokens').to_numpy(zero_copy_only=False)
                for field in FIELDS:
                    values=batch.column(field).to_numpy(zero_copy_only=False)
                    if np.any(values==255):raise ValueError(f'Unpublished annotation category: {field}')
                    arr[field][pos:pos+n]=values
                pos+=n
            if pos!=s['records']:raise ValueError(f"Incomplete source {s['id']}: {pos}/{s['records']}")
            arr.flush();del arr;conn.close();partial.replace(dest)
            print(f"{d['id']}/{s['id']}: {pos:,} joined records",flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(prepare,sorted(d['sources'],key=lambda s:s['id'])))
        if prepare_only:continue
        dest=OUT/(d['id']+'.npy');arr=np.lib.format.open_memmap(dest.with_suffix('.partial.npy'),mode='w+',dtype=DTYPE,shape=(d['records'],));offset=0;sources=[]
        for s in sorted(d['sources'],key=lambda s:s['id']):
            part=np.load(folder/(s['id']+'.npy'),mmap_mode='r');arr[offset:offset+len(part)]=part
            sources.append({'id':s['id'],'offset':offset,'records':len(part)});offset+=len(part)
        for field, values in labels.items():
            counts=np.zeros(len(values)+1,dtype=np.int64)
            for begin in range(0,len(arr),250_000):
                counts+=np.bincount(arr[field][begin:begin+250_000],minlength=len(counts))
            for value,code in values.items():
                if int(counts[code]) != d['annotation_distributions'][field][value]:
                    raise ValueError(f'Annotation count mismatch: {d["id"]}/{field}/{value}')
        arr.flush();del arr;dest.with_suffix('.partial.npy').replace(dest)
        with dest.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        result['languages'][d['id']]={'revision':d['revision'],'records':offset,'labels':labels,'sources':sources,'path':dest.name,'bytes':dest.stat().st_size,'sha256':digest}
        (OUT/'manifest.pending.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'manifest.pending.json').replace(OUT/'manifest.json');print(f"Ready: {d['id']} {offset:,} records",flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only',choices=['norwegian','icelandic','faroese'])
    build(parser.parse_args().prepare_only)
