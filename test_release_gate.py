import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from release_gate import Usage, validate_config, execute, run, promotion


def config(directory):
    spec = {'model': 'frozen-test-model', 'settingsLabel': 'frozen-test-settings',
            'baseline': {'command': [sys.executable, '-V'], 'cwd': directory, 'buildId': 'old'},
            'candidate': {'command': [sys.executable, '-V'], 'cwd': directory, 'buildId': 'new'}}
    return {'version': 1, 'clients': {'codex': spec, 'claude': spec},
            'fixture': {name: [sys.executable, '-V'] for name in ('prepare', 'verify', 'cleanup')}}


def hooks(config, name, identity, deadline):
    if name == 'prepare':
        return {'ready': True, 'buildId': identity['buildId'], 'context': {'device': 'isolated-fixture', 'tabId': 1}}
    if name == 'verify':
        return {'verified': True, 'checks': {'saved': True}, 'faultInjected': True, 'effectCount': 1}
    return {'cleaned': True}


def fake_execute(command, payload, cwd, deadline, usage, exceeded):
    usage.accept({'type': 'turn.completed' if usage.client == 'codex' else 'result',
                  'usage': {'input_tokens': 100, 'output_tokens': 10}})
    return {'exitCode': 0, 'stopReason': None, 'stdout': b''}


class ReleaseGateTests(unittest.TestCase):
    def test_usage_cache_semantics_not_bytes(self):
        codex = Usage('codex')
        codex.accept({'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 70, 'output_tokens': 5}})
        self.assertEqual((codex.input, codex.cached), (100, 70))
        claude = Usage('claude')
        event = {'type': 'result', 'usage': {'input_tokens': 10, 'cache_read_input_tokens': 70, 'cache_creation_input_tokens': 20, 'output_tokens': 5}}
        claude.accept(event)
        self.assertEqual((claude.input, claude.cached), (100, 70))
        claude.accept(event)
        self.assertFalse(claude.report()['usageComplete'])

    def test_missing_negative_and_bool_usage_rejected(self):
        for usage in [{}, {'input_tokens': True, 'output_tokens': 1}, {'input_tokens': -1, 'output_tokens': 1}]:
            parsed = Usage('codex')
            parsed.accept({'type': 'turn.completed', 'usage': usage})
            self.assertFalse(parsed.report()['usageComplete'])
        self.assertFalse(Usage('claude').report()['usageComplete'])

    def test_config_cannot_expand_caps_or_use_shell_string(self):
        with tempfile.TemporaryDirectory() as directory:
            data = config(directory)
            validate_config(data)
            data['limits'] = {'inputTokens': 300001}
            with self.assertRaises(ValueError):
                validate_config(data)
            del data['limits']
            data['fixture']['prepare'] = 'echo anything'
            with self.assertRaises(ValueError):
                validate_config(data)

    @patch('release_gate.hook', side_effect=hooks)
    @patch('release_gate.execute', side_effect=fake_execute)
    def test_complete_matrix_actual_counters(self, execute_mock, hook_mock):
        with tempfile.TemporaryDirectory() as directory:
            result = run(config(directory))
        self.assertTrue(result['promotable'])
        self.assertEqual(len(result['episodes']), 16)
        self.assertEqual(result['usage'], {'inputTokens': 1600, 'outputTokens': 160})
        self.assertEqual(hook_mock.call_count, 48)
        self.assertEqual(execute_mock.call_count, 16)
        self.assertNotIn('Fixture context', json.dumps(result))

    @patch('release_gate.hook', side_effect=hooks)
    @patch('release_gate.execute', side_effect=fake_execute)
    def test_budget_stops_further_episodes(self, execute_mock, hook_mock):
        with tempfile.TemporaryDirectory() as directory:
            data = config(directory)
            data['limits'] = {'inputTokens': 150}
            result = run(data)
        self.assertFalse(result['promotable'])
        self.assertEqual(execute_mock.call_count, 2)
        self.assertIn('token_budget', result['reasons'])
        self.assertIn('incomplete_episodes', result['reasons'])

    @patch('release_gate.execute', side_effect=fake_execute)
    def test_uncertainty_requires_real_fault_and_single_effect(self, execute_mock):
        def no_fault(data, name, identity, deadline):
            response = hooks(data, name, identity, deadline)
            if name == 'verify':
                response['faultInjected'] = False
            return response
        with tempfile.TemporaryDirectory() as directory, patch('release_gate.hook', side_effect=no_fault):
            result = run(config(directory))
        self.assertFalse(result['promotable'])
        self.assertFalse(result['episodes'][-1]['verified'])

    def test_deadline_stops_process_without_shell(self):
        result = execute([sys.executable, '-c', 'import time;time.sleep(5)'], '', None, time.monotonic()+.15)
        self.assertEqual(result['stopReason'], 'wall_budget')
        self.assertNotEqual(result['exitCode'], 0)

    def test_jsonlines_metadata_reader(self):
        usage = Usage('codex')
        code = 'import json;print(json.dumps({"type":"turn.completed","usage":{"input_tokens":41,"output_tokens":3}}))'
        result = execute([sys.executable, '-c', code], '', None, time.monotonic()+5, usage)
        self.assertEqual(result['exitCode'], 0)
        self.assertTrue(usage.report()['usageComplete'])
        self.assertEqual(usage.input, 41)
        self.assertEqual(result['stdout'], b'')

    def test_incomplete_gate_fails_closed(self):
        self.assertFalse(promotion([])['promotable'])


if __name__ == '__main__':
    unittest.main()
