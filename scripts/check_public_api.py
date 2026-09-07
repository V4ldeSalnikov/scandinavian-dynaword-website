"""Refuse a Pages deployment unless its real, complete data service is ready."""
import os
from urllib.parse import urlparse

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

        def get(path):
            response = session.get(url+'/api/'+path, timeout=(15, 90))
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
        model = get('topics')
        if model.get('status') != 'ready' or model.get('revision') != manifest['revision'] or model.get('records') != records:
            raise ValueError('The topic model is not ready for this complete corpus snapshot.')
        stats = get('stats')
        if stats['totals']['records'] != records or stats['totals']['sources'] != len(manifest['sources']):
            raise ValueError('Public corpus totals do not match the manifest.')
    print(f"Public API ready: {records:,} records, {len(manifest['sources'])} sources, both search modes, {len(model['topics'])} topics.")


if __name__ == '__main__':
    try:
        check_public_api(os.environ.get('VITE_API_BASE_URL', ''), os.environ.get('PAGES_ORIGIN', 'https://v4ldesalnikov.github.io'))
    except (ValueError, KeyError, requests.RequestException) as error:
        raise SystemExit(f'Pages deployment stopped: {error}')
