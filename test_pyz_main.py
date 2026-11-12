import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

import pyz_main

ROOT = Path(__file__).resolve().parent


def make_archive(path, launcher='print("ok")'):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('launcher.py', launcher)
        archive.writestr('__main__.py', (ROOT / 'pyz_main.py').read_text())


class CachedExtractionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name) / 'cache'
        self.archive = Path(self.temporary.name) / 'a.pyz'
        make_archive(self.archive)

    def tearDown(self):
        self.temporary.cleanup()

    def test_reuses_one_private_extraction_per_archive(self):
        first = pyz_main.cached_extraction(self.archive, self.base)
        self.assertTrue((first / 'launcher.py').is_file())
        self.assertEqual(first.stat().st_mode & 0o777, 0o700)
        marker = first / 'marker'
        marker.write_text('kept')
        self.assertEqual(pyz_main.cached_extraction(self.archive, self.base), first)
        self.assertTrue(marker.exists())
        self.assertEqual([p.name for p in self.base.iterdir()], [first.name])

    def test_new_archive_content_gets_new_directory(self):
        first = pyz_main.cached_extraction(self.archive, self.base)
        make_archive(self.archive, 'print("changed")')
        second = pyz_main.cached_extraction(self.archive, self.base)
        self.assertNotEqual(first, second)
        self.assertIn('changed', (second / 'launcher.py').read_text())

    def test_shared_cache_directory_is_refused(self):
        self.base.mkdir(mode=0o755)
        os.chmod(self.base, 0o755)
        self.assertIsNone(pyz_main.cached_extraction(self.archive, self.base))

    def test_symlinked_cache_directory_is_refused(self):
        real = Path(self.temporary.name) / 'real'
        real.mkdir(mode=0o700)
        self.base.symlink_to(real)
        self.assertIsNone(pyz_main.cached_extraction(self.archive, self.base))

    def test_invalid_archive_returns_none(self):
        self.archive.write_bytes(b'not a zip')
        self.assertIsNone(pyz_main.cached_extraction(self.archive, self.base))

    def test_concurrent_starts_share_one_complete_copy(self):
        env = dict(os.environ, XDG_CACHE_HOME=str(self.base))
        processes = [subprocess.Popen([sys.executable, str(self.archive)], env=env, stdout=subprocess.PIPE, text=True)
                     for _ in range(6)]
        outputs = [process.communicate(timeout=30)[0] for process in processes]
        self.assertEqual(outputs, ['ok\n'] * 6)
        entries = list((self.base / pyz_main.CACHE_NAME).iterdir())
        self.assertEqual(len(entries), 1, entries)

    def test_unusable_cache_falls_back_to_temporary_extraction(self):
        blocked = Path(self.temporary.name) / 'file'
        blocked.write_text('')
        env = dict(os.environ, XDG_CACHE_HOME=str(blocked))
        result = subprocess.run([sys.executable, str(self.archive)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.stdout, 'ok\n', result.stderr)


class BuiltPackageTest(unittest.TestCase):
    def test_package_entry_point_is_pyz_main(self):
        package = ROOT / 'android-browser-mcp.pyz'
        if not package.exists():
            self.skipTest('run python3 build.py first')
        with zipfile.ZipFile(package) as archive:
            self.assertEqual(archive.read('__main__.py').decode(), (ROOT / 'pyz_main.py').read_text())

    def test_package_starts_from_cache_and_answers_initialize(self):
        package = ROOT / 'android-browser-mcp.pyz'
        if not package.exists():
            self.skipTest('run python3 build.py first')
        with tempfile.TemporaryDirectory() as directory:
            connection = Path(directory) / 'c.json'
            descriptor = os.open(connection, os.O_WRONLY | os.O_CREAT, 0o600)
            os.write(descriptor, json.dumps({'url': 'http://127.0.0.1:9', 'token': 'x' * 40}).encode())
            os.close(descriptor)
            env = dict(os.environ, XDG_CACHE_HOME=str(Path(directory) / 'cache'))
            request = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}}) + '\n'
            replies = []
            for _ in range(2):
                started = time.monotonic()
                result = subprocess.run([sys.executable, str(package), '--connection-file', str(connection)], input=request,
                                        env=env, capture_output=True, text=True, timeout=60)
                replies.append(json.loads(result.stdout.splitlines()[0]))
                self.assertLess(time.monotonic() - started, 30)
            self.assertEqual(replies[0], replies[1])
            self.assertEqual(replies[0]['result']['serverInfo']['name'], 'android-browser-bridge')
            cached = list((Path(directory) / 'cache' / pyz_main.CACHE_NAME).iterdir())
            self.assertEqual(len(cached), 1)
            self.assertTrue(any(cached[0].joinpath('__pycache__').iterdir()))


if __name__ == '__main__':
    unittest.main()
