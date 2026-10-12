import base64
import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from browser_cli import execute


class Client:
    def __init__(self, result):
        self.result = result
        self.closed = False
        self.calls = []
    def rpc(self, method, params):
        self.calls.append((method, params))
        return self.result
    def close(self):
        self.closed = True


class BrowserCliTests(unittest.TestCase):
    def test_reuses_tool_contract_and_closes(self):
        client = Client({'content': [{'type': 'text', 'text': '{"devices":[]}'}]})
        result = execute({'operation': 'devices'}, lambda: client)
        self.assertEqual(client.calls, [('tools/call', {'name': 'browser_devices', 'arguments': {}})])
        self.assertTrue(client.closed)
        self.assertEqual(json.loads(result['content'][0]['text']), {'devices': []})

    def test_images_are_private_artifacts(self):
        client = Client({'content': [{'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(b'fixture-image').decode()}]})
        with tempfile.TemporaryDirectory() as directory:
            result = execute({'operation': 'command', 'arguments': {'device': 'fixture', 'op': 'screenshot', 'args': {'tabId': 1}}}, lambda: client, directory)
            block = result['content'][0]
            self.assertEqual(block['type'], 'artifact')
            self.assertEqual(Path(block['path']).read_bytes(), b'fixture-image')
            self.assertEqual(os.stat(block['path']).st_mode & 0o777, 0o600)
            self.assertNotIn('data', block)

    def test_no_client_spawn_for_invalid_or_discovery(self):
        def forbidden():
            self.fail('Must not start client')
        for request in [{'operation': 'pair'}, {'operation': 'command', 'arguments': {'op': 'click'}}, {'operation': 'devices', 'arguments': {'token': 'secret'}}]:
            with self.assertRaises(ValueError):
                execute(request, forbidden)
        self.assertIn('browserOperations', execute({'operation': 'discover'}, forbidden))

    def test_native_artifact_goes_to_explicit_private_file_only(self):
        payload = b'private-fixture-not-model-text'
        identifier = 'a'*64
        def transport(arguments):
            self.assertEqual(arguments, {'device':'tablet','artifactId':identifier})
            return {'device':'tablet','artifactId':identifier,'size':len(payload),
                    'sha256':hashlib.sha256(payload).hexdigest(), 'dataBase64':base64.b64encode(payload).decode()}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'shared.bin'
            request = {'operation':'artifact','arguments':{'device':'tablet','artifactId':identifier,'output':str(output)}}
            result = execute(request, artifact_transport=transport)
            self.assertEqual(output.read_bytes(),payload)
            self.assertEqual(output.stat().st_mode&0o777,0o600)
            self.assertNotIn('dataBase64',str(result))
            self.assertNotIn(payload.decode(),str(result))
            with self.assertRaises(FileExistsError):execute(request, artifact_transport=transport)
            request['arguments']['output']='-'
            with self.assertRaises(ValueError):execute(request, artifact_transport=transport)

    def test_machine_readable_failure_does_not_echo_input(self):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('browser_cli.py'))], input='not-json-secret', text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(json.loads(result.stdout)['isError'])
        self.assertNotIn('not-json-secret', result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
