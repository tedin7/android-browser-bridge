"""fill/type with valueFile: the secret goes from a server file to the field without passing through the model."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import mcp_server

SECRET = 'S3gr3to-di-prova-0001'


def call(**args):
    return mcp_server.handle({'id': 1, 'method': 'tools/call', 'params': {'name': 'browser_command', 'arguments': args}})


class SecretFillTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        root.chmod(0o700)
        self.file = root / 'sito.txt'
        self.file.write_text(SECRET + '\n')
        self.file.chmod(0o600)
        env = patch.dict(os.environ, {'BROWSER_BRIDGE_TOKEN': 'test-token', 'BROWSER_BRIDGE_SECRET_DIR': str(root)})
        env.start()
        self.addCleanup(env.stop)

    def run_fill(self, op='fill', **extra):
        seen = {}

        def fake(url, token, device, operation, values):
            seen.update(values)
            return {'ok': True, 'ref': 'e1', 'echo': values.get('value')}
        with patch('mcp_server.execute_browser_command', side_effect=fake):
            out = call(device='t', op=op, args={'tabId': 1, 'selector': '#p', **extra})
        return seen, out

    def test_value_reaches_field_but_not_the_model(self):
        seen, out = self.run_fill(valueFile=str(self.file))
        self.assertEqual(seen['value'], SECRET)
        self.assertNotIn('valueFile', seen)
        self.assertNotIn(SECRET, json.dumps(out))

    def test_relative_name_inside_secret_dir(self):
        seen, out = self.run_fill(valueFile='sito.txt')
        self.assertEqual(seen['value'], SECRET)

    def test_rejects_file_outside_secret_dir(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as handle:
            handle.write(SECRET)
        self.addCleanup(os.unlink, handle.name)
        os.chmod(handle.name, 0o600)
        seen, out = self.run_fill(valueFile=handle.name)
        self.assertTrue(out.get('isError'))
        self.assertEqual(seen, {})
        self.assertNotIn(SECRET, json.dumps(out))

    def test_rejects_symlink_escaping_dir(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as handle:
            handle.write(SECRET)
        self.addCleanup(os.unlink, handle.name)
        os.chmod(handle.name, 0o600)
        link = Path(self.dir.name) / 'link.txt'
        link.symlink_to(handle.name)
        seen, out = self.run_fill(valueFile=str(link))
        self.assertTrue(out.get('isError'))
        self.assertEqual(seen, {})

    def test_rejects_group_or_world_readable(self):
        self.file.chmod(0o644)
        seen, out = self.run_fill(valueFile=str(self.file))
        self.assertTrue(out.get('isError'))
        self.assertEqual(seen, {})

    def test_rejects_value_and_valuefile_together(self):
        seen, out = self.run_fill(valueFile=str(self.file), value='x')
        self.assertTrue(out.get('isError'))
        self.assertEqual(seen, {})

    def test_only_fill_and_type(self):
        seen, out = self.run_fill(op='click', valueFile=str(self.file))
        self.assertTrue(out.get('isError'))
        self.assertEqual(seen, {})

    def test_missing_file_error_has_no_secret(self):
        seen, out = self.run_fill(valueFile='manca.txt')
        self.assertTrue(out.get('isError'))
        self.assertEqual(seen, {})

    def test_works_inside_batch_step(self):
        seen = {}

        def fake(url, token, device, operation, values):
            seen.update(values)
            return {'results': [], 'completed': 1, 'echo': json.dumps(values)}
        with patch('mcp_server.execute_browser_command', side_effect=fake):
            out = call(device='t', op='batch', args={'tabId': 1, 'steps': [{'op': 'fill', 'args': {'selector': '#p', 'valueFile': 'sito.txt'}}]})
        self.assertEqual(seen['steps'][0]['args']['value'], SECRET)
        self.assertNotIn(SECRET, json.dumps(out))


if __name__ == '__main__':
    unittest.main()
