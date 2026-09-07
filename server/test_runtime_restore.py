import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from scripts.restore_runtime import destination, download, restore
from scripts.package_runtime import check_snapshot


class RuntimeRestoreTests(unittest.TestCase):
    def test_partial_or_mixed_snapshots_cannot_be_packaged(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {'revision': 'snapshot', 'records': 4}
            text = {'status': 'ready', 'revision': 'snapshot', 'records': 4}
            semantic = {**text, 'records_processed': 4, 'records_with_vectors': 3, 'metadata_fingerprint': 'same'}
            topics = {**text, 'assigned': 3, 'metadata_fingerprint': 'same'}
            for name, state in [('search_manifest.json', text), ('semantic_manifest.json', semantic), ('topics_manifest.json', topics)]:
                (root / name).write_text(json.dumps(state))
            check_snapshot(root, manifest)
            (root / 'search_manifest.json').write_text(json.dumps({**text, 'records': 3}))
            with self.assertRaisesRegex(ValueError, 'complete, ready'):
                check_snapshot(root, manifest)
            (root / 'search_manifest.json').write_text(json.dumps(text))
            (root / 'topics_manifest.json').write_text(json.dumps({**topics, 'metadata_fingerprint': 'other'}))
            with self.assertRaisesRegex(ValueError, 'different snapshots'):
                check_snapshot(root, manifest)

    def test_download_verifies_content_before_installing(self):
        entry = {'path': 'index/data', 'bytes': 4, 'sha256': hashlib.sha256(b'data').hexdigest()}
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b'fail']
        with TemporaryDirectory() as folder, patch('scripts.restore_runtime.requests.get', return_value=response), patch('scripts.restore_runtime.time.sleep'):
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, 'Integrity check'):
                download('https://example.org/', root, entry)
            self.assertFalse((root / 'index/data').exists())
            self.assertFalse((root / 'index/data.download').exists())
            response.iter_content.return_value = [b'data']
            self.assertEqual(download('https://example.org/', root, entry), 4)
            self.assertEqual((root / 'index/data').read_bytes(), b'data')

    def test_inventory_cannot_escape_destination(self):
        with TemporaryDirectory() as folder:
            for path in ['../outside', '/outside', 'index/../../outside']:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    destination(Path(folder), {'path': path})

    def test_failed_restore_never_leaves_a_ready_manifest(self):
        inventory = {'version': 1, 'dataset': 'danish-foundation-models/danish-dynaword', 'files': [
            {'path': 'manifest.json'}, {'path': 'corpus.duckdb'}]}
        response = MagicMock()
        response.json.return_value = inventory
        with TemporaryDirectory() as folder, patch('scripts.restore_runtime.requests.get', return_value=response), patch('scripts.restore_runtime.download', side_effect=ValueError('bad checksum')):
            root = Path(folder)
            (root / 'manifest.json').write_text('{"status":"ready"}')
            with self.assertRaisesRegex(ValueError, 'bad checksum'):
                restore({'repo': 'owner/index', 'revision': 'a' * 40}, root)
            self.assertFalse((root / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
