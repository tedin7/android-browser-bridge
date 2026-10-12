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
