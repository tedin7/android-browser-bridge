import copy
import unittest
from protocol_adapter import MODERN_VERSION, PREFIX, ProtocolAdapter, ProtocolError


class ProtocolAdapterTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.result = {"content": [{"type": "text", "text": "ok"}]}
        def legacy(message):
            self.calls.append(copy.deepcopy(message))
            if message["method"] == "initialize":
                return {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
            if message["method"] == "tools/list":
                return {"tools": [{"name": "z"}, {"name": "a"}]}
            return self.result
        self.adapter = ProtocolAdapter(legacy, server_info={"name": "fixture", "version": "1.0"})

    def request(self, method, version=MODERN_VERSION):
        return {"jsonrpc": "2.0", "id": 1, "method": method, "params": {"_meta": {
            PREFIX + "protocolVersion": version, PREFIX + "clientCapabilities": {}}}}

    def test_stateless_discovery_and_tools(self):
        result = self.adapter.handle(self.request("server/discover"))
        self.assertEqual(result["supportedVersions"][0], MODERN_VERSION)
        self.assertEqual(result["capabilities"], {"tools": {}})
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["cacheScope"], "private")
        self.assertEqual(self.calls, [])
        listing = self.adapter.handle(self.request("tools/list"))
        self.assertEqual([tool["name"] for tool in listing["tools"]], ["a", "z"])
        self.assertEqual(listing["ttlMs"], 60000)
        result = self.adapter.handle(self.request("tools/call"))
        self.assertEqual(result["_meta"][PREFIX + "serverInfo"]["name"], "fixture")
        self.assertNotIn("resultType", self.result)
        self.assertNotIn("ttlMs", result)

    def test_missing_fields_unknown_version_and_methods_fail_before_handler(self):
        for message, expected in ((self.request("tools/call", "unknown"), -32022),
                                  ({"id": 1, "method": "tools/call"}, -32602),
                                  (self.request("tasks/get"), -32601),
                                  (self.request("ping"), -32601)):
            with self.assertRaises(ProtocolError) as raised:
                self.adapter.handle(message)
            self.assertEqual(raised.exception.code, expected)
            if expected == -32022:
                self.assertEqual(raised.exception.data["requested"], "unknown")
                self.assertIn(MODERN_VERSION, raised.exception.data["supported"])
        message = self.request("tools/call")
        del message["params"]["_meta"][PREFIX + "clientCapabilities"]
        with self.assertRaises(ProtocolError) as raised:
            self.adapter.handle(message)
        self.assertEqual(raised.exception.code, -32602)
        self.assertEqual(self.calls, [])

    def test_legacy_unchanged_and_modern_not_sticky(self):
        initialize = {"id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}
        result = self.adapter.handle(initialize)
        self.assertEqual(self.calls[-1], initialize)
        self.assertNotIn("resultType", result)
        self.adapter.handle(self.request("server/discover"))
        result = self.adapter.handle({"id": 2, "method": "tools/call"})
        self.assertIs(result, self.result)
        message = self.request("tools/call")
        del message["params"]["_meta"][PREFIX + "clientCapabilities"]
        with self.assertRaises(ProtocolError):
            self.adapter.handle(message)

    def test_resources_and_tasks_result_type_are_preserved(self):
        class Tasks:
            def handle(self,message):
                return {'resultType':'task','taskId':'opaque'} if message['method']=='tools/call' else None
        adapter=ProtocolAdapter(lambda message:{'resources':[]},server_info={'name':'test','version':'1'},capabilities={'tools':{},'resources':{}},tasks_adapter=Tasks())
        self.assertEqual(adapter.handle(self.request('tools/call'))['resultType'],'task')
        self.assertEqual(adapter.handle(self.request('resources/list'))['resources'],[])
        capabilities=adapter.handle(self.request('server/discover'))['capabilities']
        self.assertEqual(capabilities['extensions'],{'io.modelcontextprotocol/tasks':{}})

    def test_notifications_and_unimplemented_capabilities(self):
        self.assertIsNone(self.adapter.handle({"method": "tools/call"}))
        self.assertEqual(self.calls, [])
        with self.assertRaises(ValueError):
            ProtocolAdapter(lambda m: {}, server_info={"name": "x", "version": "1"}, capabilities={"tools": {}, "subscriptions": {}})


if __name__ == "__main__":
    unittest.main()
