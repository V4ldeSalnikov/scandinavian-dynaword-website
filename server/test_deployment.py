from copy import deepcopy
import unittest
from unittest.mock import MagicMock, patch

from scripts.check_public_api import check_public_api


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.origin = 'https://v4ldesalnikov.github.io'
        self.responses = {
            'manifest': {'status': 'ready', 'dataset': 'danish-foundation-models/danish-dynaword',
                         'records': 4, 'sources': ['a','b'], 'revision': 'test',
                         'search': {'text': True, 'semantic': True, 'text_index': {'records': 4}, 'semantic_index': {'records_processed': 4}}},
            'topics': {'status': 'ready', 'revision': 'test', 'records': 4, 'topics': [{},{}]},
            'stats': {'totals': {'records': 4, 'sources': 2}},
        }

    def run_check(self, bodies=None, cors=True):
        bodies = bodies or self.responses
        session = MagicMock()
        session.__enter__.return_value = session
        def response(url, **kwargs):
            result = MagicMock()
            result.headers = {'Access-Control-Allow-Origin': self.origin} if cors else {}
            result.json.return_value = bodies[url.rsplit('/',1)[-1]]
            return result
        session.get.side_effect = response
        with patch('scripts.check_public_api.requests.Session', return_value=session):
            check_public_api('https://api.example.org', self.origin)

    def test_complete_public_api_can_be_published(self):
        self.run_check()

    def test_missing_browser_access_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, 'ALLOWED_ORIGINS'):
            self.run_check(cors=False)

    def test_partial_search_and_stale_topics_block_publication(self):
        bodies = deepcopy(self.responses)
        bodies['manifest']['search']['text_index']['records'] = 3
        with self.assertRaisesRegex(ValueError, 'complete corpus'):
            self.run_check(bodies)
        bodies = deepcopy(self.responses)
        bodies['topics']['revision'] = 'old'
        with self.assertRaisesRegex(ValueError, 'topic model'):
            self.run_check(bodies)

    def test_local_or_credential_bearing_urls_are_not_public_api_origins(self):
        for url in ['', 'http://localhost:8000', 'https://localhost', 'https://api.example.org/api', 'https://user:password@api.example.org']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                check_public_api(url, self.origin)


if __name__ == '__main__':
    unittest.main()
