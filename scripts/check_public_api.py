"""Refuse a Pages deployment unless its real, complete data service is ready."""
import os
import json
import time
from pathlib import Path
from urllib.parse import urlparse, urlencode

import requests


def check_public_api(api_url, pages_origin):
    url = api_url.rstrip('/')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('VITE_API_BASE_URL must be a public HTTPS origin, without credentials, a path, or query parameters.')
    if parsed.hostname.lower() in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('GitHub Pages needs a public API, not a localhost address.')
    origin = pages_origin.lower().rstrip('/')
    with requests.Session() as session:
        session.headers['Origin'] = origin
        session.headers['Cache-Control'] = 'no-cache'

        def get(path):
            # A cached successful response must not hide an unavailable new API.
            response = session.get(url+'/api/'+path, params={'_check':time.time_ns()}, timeout=(15, 90))
            response.raise_for_status()
            if response.headers.get('Access-Control-Allow-Origin') not in {origin, '*'}:
                raise ValueError('The API must allow the GitHub Pages origin through ALLOWED_ORIGINS.')
            return response.json()

        manifest = get('manifest')
        if manifest.get('status') != 'ready' or manifest.get('dataset') != 'danish-foundation-models/danish-dynaword':
            raise ValueError('The Danish corpus API is not ready.')
        records = manifest['records']
        search = manifest.get('search', {})
        if not search.get('text') or not search.get('semantic'):
            raise ValueError('Both full-corpus search indexes must be ready before publication.')
        if search['text_index']['records'] != records or search['semantic_index']['records_processed'] != records:
            raise ValueError('The search indexes do not cover the complete corpus.')
        stats = get('stats')
        if stats['totals']['records'] != records or stats['totals']['sources'] != len(manifest['sources']):
            raise ValueError('Public corpus totals do not match the manifest.')
        catalog=json.loads((Path(__file__).resolve().parents[1]/'web/public/data/corpora.json').read_text())
        for corpus in catalog['datasets']:
            if corpus['id']=='danish':continue
            selection=get('corpora/'+corpus['id']+'/stats')
            if selection['totals']['records']!=corpus['records'] or selection['totals']['tokens']!=corpus['tokens']:
                raise ValueError('The '+corpus['id']+' selection statistics do not cover the complete release.')
            path='corpora/'+corpus['id']+'/rows?'
            page=get(path+urlencode({'limit':1}))
            if page.get('total')!=corpus['records'] or len(page.get('rows',[]))!=1:
                raise ValueError('The '+corpus['id']+' explorer does not cover the complete release.')
            if corpus['annotation_distributions']:
                page=get(path+urlencode({'limit':1,'filters':json.dumps({'annotations':{'educational_value':'high'}})}))
                if page.get('total')!=corpus['annotation_distributions']['educational_value']['high'] or len(page.get('rows',[]))!=1:
                    raise ValueError('The '+corpus['id']+' annotation index is not ready.')
    print(f"Public API ready: all five explorers; Danish {records:,} records, {len(manifest['sources'])} sources, both search modes.")


if __name__ == '__main__':
    deadline=time.monotonic()+int(os.environ.get('PUBLIC_API_WAIT_SECONDS','0'))
    waiting=False
    while True:
        try:
            check_public_api(os.environ.get('VITE_API_BASE_URL', ''), os.environ.get('PAGES_ORIGIN', 'https://v4ldesalnikov.github.io'))
            break
        except requests.RequestException as error:
            if time.monotonic()>=deadline:
                raise SystemExit(f'Pages deployment stopped: {error}')
            if not waiting:print('Waiting for the updated language API before publishing Pages…',flush=True);waiting=True
            time.sleep(20)
        except (ValueError, KeyError) as error:
            raise SystemExit(f'Pages deployment stopped: {error}')
