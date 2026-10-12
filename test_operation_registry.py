"""Cross-adapter drift checks and pre-dispatch structural contract regressions."""
import json
import re
import unittest
from pathlib import Path

from operation_registry import OPERATIONS, PAGE_OPERATIONS, BACKGROUND_OPERATIONS, PRODUCT_VERSION, validate_arguments, operation_contract, _validate
from generate_operations import outputs

ROOT = Path(__file__).resolve().parent


class OperationRegistryTests(unittest.TestCase):
    def test_catalog_matches_broker_and_mcp(self):
        import bridge
        import mcp_server
        self.assertEqual(OPERATIONS, bridge.OPERATIONS)
        command = next(tool for tool in mcp_server.TOOLS if tool['name'] == 'browser_command')
        self.assertEqual(OPERATIONS, set(command['inputSchema']['properties']['op']['enum']))

    def test_catalog_matches_extension_dispatch(self):
        source = (ROOT / 'extension/background.js').read_text()
        for variable, expected in [('PAGE_OPERATIONS', PAGE_OPERATIONS), ('TAB_OPERATIONS', BACKGROUND_OPERATIONS)]:
            match = re.search(r'const ' + variable + r' = new Set\((\[.*?\])\)', source)
            if match:  # Legacy constants until the adapter adopts the generated catalog.
                self.assertEqual(expected, set(json.loads(match.group(1))))
            else:
                self.assertIn('BrowserBridgeOperations', source)
                self.assertIn('operations.generated.js', (ROOT / 'extension/manifest.json').read_text())
        manifest = json.loads((ROOT / 'extension/manifest.json').read_text())
        self.assertEqual(PRODUCT_VERSION, manifest['version'])

    def test_generated_contracts_current(self):
        for path, expected in outputs().items():
            self.assertEqual(expected, path.read_text(), str(path))

    def test_batch_rejects_invalid_later_step_before_dispatch(self):
        for invalid in [
            {'op': 'viewport', 'args': {'width': True, 'height': 720}},
            {'op': 'fill', 'args': {'selector': '#name', 'value': [], 'force': True}},
            {'op': 'click', 'args': {'selector': '#buy', 'script': 'anything'}},
            {'op': 'batch', 'args': {'steps': [{'op': 'tabs'}]}},
            {'op': 'scroll', 'args': {'x': float('nan')}},
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_arguments('batch', {'steps': [{'op': 'click', 'args': {'selector': '#buy'}}, invalid]})

    def test_batch_errors_name_step_and_accepted_targets(self):
        steps = [{'op': 'read', 'args': {}}, {'op': 'press', 'args': {'key': 'End'}}]
        with self.assertRaisesRegex(ValueError, r'^steps\[1\] press: args: needs one of selector, ref, role'):
            validate_arguments('batch', {'tabId': 1, 'steps': steps})

    def test_broker_reports_invalid_arguments_as_precondition(self):
        from bridge import BrokerError
        from mcp_guidance import failure
        detail = failure(BrokerError('INVALID_ARGUMENT', 'steps[1] press: args: needs one of selector'), 'pad', 'batch')
        self.assertEqual(detail['code'], 'INVALID_ARGUMENT')
        self.assertFalse(detail['actionMayHaveOccurred'])
        # Over HTTP the broker body becomes "CODE: message".
        detail = failure(RuntimeError('INVALID_ARGUMENT: steps[1] press: args: needs one of selector'), 'pad', 'batch')
        self.assertEqual(detail['code'], 'INVALID_ARGUMENT')
        self.assertFalse(detail['actionMayHaveOccurred'])

    def test_platform_checked_recursively(self):
        command = {'steps': [{'op': 'viewport', 'args': {'width': 1280, 'height': 720}}]}
        validate_arguments('batch', command, platform='firefox-desktop')
        with self.assertRaises(ValueError):
            validate_arguments('batch', command, platform='firefox-android')

    def test_preserves_legacy_defaults_and_references(self):
        for op, args in [('fill', {'ref': 'epoch-e3'}), ('check', {'role': 'checkbox'}),
                         ('read', {'text': False, 'maxElements': 0}), ('tabs', {}),
                         ('drag', {'x': 0, 'y': 0, 'toX': 10, 'toY': 10, 'steps': 4}),
                         ('batch', {'tabId': 19, 'steps': [{'op': 'click', 'args': {'name': 'Save'}}]})]:
            before = json.dumps(args, sort_keys=True)
            self.assertIs(args, validate_arguments(op, args))
            self.assertEqual(before, json.dumps(args, sort_keys=True))

    def test_string_bounds_pattern_and_boolean_enum_are_enforced(self):
        validate_arguments('acquire_lease', {'tabId': 1, 'workflowId': 'run-123'})
        for workflow in ('', 'spaces not allowed', 'x' * 129):
            with self.assertRaises(ValueError):
                validate_arguments('acquire_lease', {'tabId': 1, 'workflowId': workflow})
        for generation in ('', 'x' * 257):
            with self.assertRaises(ValueError):
                validate_arguments('release_lease', {'tabId': 1, 'workflowId': 'run', 'leaseGeneration': generation})
        with self.assertRaises(ValueError):
            _validate({'enum': [1]}, True, 'test')
        with self.assertRaises(ValueError):
            _validate({'enum': [False]}, 0, 'test')
        _validate({'enum': [1]}, 1.0, 'test')

    def test_contract_copy_and_unknown_operation(self):
        contract = operation_contract('tabs')
        contract['platforms'].clear()
        self.assertTrue(operation_contract('tabs')['platforms'])
        with self.assertRaises(ValueError):
            validate_arguments('evaluate', {'script': '1 + 1'})


if __name__ == '__main__':
    unittest.main()
