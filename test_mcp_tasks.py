import copy
import unittest
from mcp_tasks import MCPTasksAdapter, EXTENSION
from protocol_adapter import MODERN_VERSION, PREFIX, ProtocolError


class MCPTasksTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.record = {"taskId": "fixture-task", "state": "working", "createdAt": 100, "updatedAt": 101, "expiresAt": 200, "receipt": {}}
        def start(args):
            self.calls.append(("start", args))
            return copy.deepcopy(self.record)
        def get(args):
            self.calls.append(("get", args))
            return copy.deepcopy(self.record)
        def cancel(args):
            self.calls.append(("cancel", args))
        self.serializer = lambda receipt: {"content": [{"type": "text", "text": str(receipt)}]}
        self.adapter = MCPTasksAdapter(start, get, cancel, self.serializer)

    def request(self, method, **params):
        return {"id": 1, "method": method, "params": {"_meta": {
            PREFIX + "protocolVersion": MODERN_VERSION,
            PREFIX + "clientCapabilities": {"extensions": {EXTENSION: {}}}}, **params}}

    def test_creation_shape_and_no_client_optin(self):
        message = self.request("tools/call", name="browser_step", arguments={"device": "tablet", "plan": {"tabId": 7, "steps": [{"op": "read"}]}})
        result = self.adapter.handle(message)
        self.assertEqual(result["resultType"], "task")
        self.assertEqual(result["ttlMs"], 100000)
        self.assertEqual(result["createdAt"], "1970-01-01T00:01:40.000Z")
        self.assertNotIn("task", result)
        self.assertTrue(self.calls[0][1]["retainResult"])
        message["params"]["_meta"][PREFIX + "clientCapabilities"] = {}
        self.assertIsNone(self.adapter.handle(message))
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(ProtocolError) as failure:
            self.adapter.handle({"method": "tasks/get", "params": {"taskId": "fixture-task"}})
        self.assertEqual(failure.exception.code, -32021)

    def test_completion_matches_sync_result_unknown_remains_failure(self):
        self.record.update(state="completed", result={"state": "verified", "output": {"text": "requested"}})
        result = self.adapter.handle(self.request("tasks/get", taskId="fixture-task"))
        self.assertEqual(result["result"], {**self.serializer(self.record["result"]), "resultType": "complete"})
        self.record.update(state="unknown", receipt={"actionMayHaveOccurred": True})
        result = self.adapter.handle(self.request("tasks/get", taskId="fixture-task"))
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["error"]["data"]["outcomeUnknown"])
        self.assertNotIn("result", result)

    def test_cancel_update_and_bad_plan(self):
        result = self.adapter.handle(self.request("tasks/cancel", taskId="fixture-task"))
        self.assertEqual(result, {"resultType": "complete"})
        self.assertEqual(self.record["state"], "working")
        self.assertEqual(self.adapter.handle(self.request("tasks/update", taskId="fixture-task", inputResponses={"unknown": {"result": {}}})), {"resultType": "complete"})
        before = len(self.calls)
        with self.assertRaises(ProtocolError):
            self.adapter.handle(self.request("tools/call", name="browser_step", arguments={"device": "tablet", "plan": {"steps": [{"op": "eval"}]}}))
        self.assertEqual(len(self.calls), before)


if __name__ == "__main__":
    unittest.main()
