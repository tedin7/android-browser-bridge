"""Claude user registration preserves unrelated configuration and guidance."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install
import agent_integration

ROOT = Path(__file__).resolve().parent


class ClaudeInstallTests(unittest.TestCase):
    def test_collision_preservation_private_backups_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory, patch('install.Path.home', return_value=Path(directory)):
            path = Path(directory)/'.claude.json'
            original = {'projects': {'/project': {'allowedTools': ['Keep']}}, 'theme': 'dark', 'mcpServers': {'android-browser': {'command': 'unrelated'}, 'other': {'command': 'keep', 'env': {'SECRET': 'fixture'}}}}
            path.write_text(json.dumps(original))
            server = {'command': 'python3', 'args': [str(ROOT/'mcp_server.py'), '--connection-file', '/private/profile']}
            name = install.register_claude(server)
            self.assertEqual(name, 'android-browser-2')
            value = json.loads(path.read_text())
            self.assertEqual(value['projects'], original['projects'])
            self.assertEqual(value['mcpServers']['android-browser'], original['mcpServers']['android-browser'])
            self.assertEqual(value['mcpServers']['other'], original['mcpServers']['other'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            backups = list(path.parent.glob('.claude.json.bak-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text()), original)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(install.register_claude(server), name)
            self.assertEqual(len(list(path.parent.glob('.claude.json.bak-*'))), 1)

    def test_own_env_preserved_credentials_migrated_and_invalid_json_untouched(self):
        with tempfile.TemporaryDirectory() as directory, patch('install.Path.home', return_value=Path(directory)):
            path = Path(directory)/'.claude.json'
            old = {'command': 'python3', 'args': [str(ROOT/'mcp_server.py')], 'env': {'BROWSER_BRIDGE_ANDROID_DEVICE': 'device', 'KEEP': 'value', 'BROWSER_BRIDGE_TOKEN': 'old-secret'}}
            path.write_text(json.dumps({'mcpServers': {'android-browser': old}}))
            install.register_claude({'command': 'python3', 'args': [str(ROOT/'mcp_server.py'), '--connection-file', '/profile']})
            env = json.loads(path.read_text())['mcpServers']['android-browser']['env']
            self.assertEqual(env, {'BROWSER_BRIDGE_ANDROID_DEVICE': 'device', 'KEEP': 'value'})
            path.write_text('invalid')
            with self.assertRaises(ValueError): install.register_claude({})
            self.assertEqual(path.read_text(), 'invalid')

    def test_observed_concurrent_edit_retries_and_preserves_new_setting(self):
        with tempfile.TemporaryDirectory() as directory, patch('install.Path.home', return_value=Path(directory)):
            path = Path(directory)/'.claude.json';path.write_text('{}')
            real_backup = install._backup
            def edit_once(target):
                if json.loads(target.read_text()) == {}:
                    target.write_text(json.dumps({'concurrent': 'preserved'}))
                real_backup(target)
            with patch('install._backup', side_effect=edit_once):
                install.register_claude({'command': 'python3', 'args': [str(ROOT/'mcp_server.py')]})
            self.assertEqual(json.loads(path.read_text())['concurrent'], 'preserved')

    def test_claude_flag_reuses_profile_and_persistent_broker(self):
        import contextlib
        import io
        import sys
        from connection import save_connection
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            profile = home/'private.json'
            save_connection({'url': 'http://127.0.0.1:19581', 'token': 'fixture-private-token'}, profile)
            (home/'.local/share/android-browser-bridge').mkdir(parents=True)
            target = home/'android-browser-mcp.pyz'
            with patch('install.Path.home', return_value=home), patch.dict(os.environ, {'BROWSER_BRIDGE_CONNECTION_FILE': str(profile)}, clear=True), patch.object(sys, 'argv', ['install.py', '--claude']), patch('install._claude_executable', return_value='/discovered/claude'), patch('install._install_package', return_value=target), patch('install.ensure_persistent_broker', return_value=profile) as broker, patch('agent_integration.install_claude_guidance', return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
                install.main()
            broker.assert_called_once()
            value = json.loads((home/'.claude.json').read_text())['mcpServers']['android-browser']
            self.assertEqual(value['args'], [str(target), '--connection-file', str(profile)])
            self.assertNotIn('fixture-private-token', output.getvalue())

    def test_guidance_preserves_user_text_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory, patch('agent_integration.Path.home', return_value=Path(directory)):
            path = Path(directory)/'.claude/CLAUDE.md';path.parent.mkdir();path.write_text('My instructions.\n')
            first = agent_integration.install_claude_guidance()
            self.assertTrue(first['updated'])
            self.assertTrue(path.read_text().startswith('My instructions.\n'))
            self.assertEqual(path.read_text().count(agent_integration.START), 1)
            self.assertFalse(agent_integration.install_claude_guidance()['updated'])
            self.assertTrue((path.parent/'skills/android-browser-bridge/SKILL.md').exists())


if __name__ == '__main__': unittest.main()
