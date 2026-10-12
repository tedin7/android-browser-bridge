import unittest
from tool_schema_policy import project_tools
from mcp_server import TOOLS

class SchemaPolicyTests(unittest.TestCase):
    def test_progressive_schema_preserves_fixed_operations_and_common_targets(self):
        projected=project_tools(TOOLS)
        full=next(t for t in TOOLS if t['name']=='browser_command')['inputSchema']['properties']
        compact=next(t for t in projected if t['name']=='browser_command')['inputSchema']['properties']
        self.assertEqual(compact['op'],full['op'])
        self.assertEqual(compact['args']['properties']['ref'],full['args']['properties']['ref'])
        self.assertTrue(compact['args']['additionalProperties'])
        self.assertNotIn('leaseGeneration',compact['args']['properties'])
        self.assertIn('leaseGeneration',full['args']['properties'])
        self.assertEqual(project_tools(TOOLS,full=True),TOOLS)


class NativePackageSchemaTests(unittest.TestCase):
    def test_compact_schema_advertises_native_package(self):
        command = next(tool for tool in project_tools(TOOLS) if tool['name'] == 'browser_command')
        package = command['inputSchema']['properties']['args']['properties']['package']
        self.assertEqual(package['type'], 'string')
        self.assertIn('Native companion', package['description'])


class TokenEconomyTests(unittest.TestCase):
    def test_scoped_clients_do_not_see_admin_tools(self):
        names = {tool['name'] for tool in project_tools(TOOLS, scoped=True)}
        self.assertFalse(names & {'browser_pair', 'browser_revoke', 'browser_metrics'})
        self.assertIn('browser_command', names)
        self.assertIn('browser_pair', {tool['name'] for tool in project_tools(TOOLS)})

    def test_compact_schema_drops_result_field_enum_only(self):
        import json
        compact = project_tools(TOOLS)
        for tool in compact:
            fields = tool['inputSchema'].get('properties', {}).get('resultFields')
            if fields:
                self.assertNotIn('enum', fields['items'])
        self.assertLess(len(json.dumps(compact)), 7500)
        full = project_tools(TOOLS, full=True)
        status = next(tool for tool in full if tool['name'] == 'browser_status')
        self.assertIn('enum', status['inputSchema']['properties']['resultFields']['items'])

    def test_misplaced_operation_arguments_are_moved_into_args(self):
        from mcp_server import normalize_command_arguments
        moved = normalize_command_arguments({'device': 'd', 'op': 'inspect', 'tabId': '10450', 'ref': 'r1'})
        self.assertEqual(moved, {'device': 'd', 'op': 'inspect', 'args': {'tabId': 10450, 'ref': 'r1'}})
        kept = normalize_command_arguments({'device': 'd', 'op': 'read', 'args': {'tabId': 2}, 'tabId': 9, 'bogus': 1})
        self.assertEqual(kept['args'], {'tabId': 2})
        self.assertEqual(kept['bogus'], 1)
