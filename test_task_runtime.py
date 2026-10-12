import threading
import tempfile
import time
import unittest
from pathlib import Path
from task_runtime import TaskRuntime
from task_store import TaskStore


class FakeBroker:
    def __init__(self):
        self.commands = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.uncertain = False

    def handle(self, path, data):
        self.commands.append(data)
        return {"id": str(len(self.commands)).zfill(16)}

    def wait_result(self, identifier, seconds, client):
        command = self.commands[int(identifier) - 1]
        assert command["_client"] == client
        if command["op"] == "acquire_lease":
            return {"state": "done", "result": {"leaseGeneration": "epoch:1"}}
        if command["op"] == "fill" and self.block:
            self.started.set()
            self.release.wait(2)
        if self.uncertain and command["op"] == "fill":
            return {"state": "dispatched"}
        return {"state": "done", "result": {"ok": True}}


class TaskRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temporary.name) / "tasks.sqlite")
        self.broker = FakeBroker()
        self.runtime = TaskRuntime(self.broker, self.store, workers=1, max_pending=2)
        self.plan = {"tabId": 7, "steps": [{"op": "fill", "args": {"selector": "#x", "value": "fixture"}}, {"op": "click", "args": {"selector": "#go"}}]}

    def tearDown(self):
        self.broker.release.set()
        self.runtime.close()
        self.store.close()
        self.temporary.cleanup()

    def await_done(self, identifier):
        for _ in range(200):
            result = self.runtime.get(identifier, "alice")
            if result["state"] != "working":
                return result
            time.sleep(.01)
        self.fail("task did not finish")

    def test_validation_scope_and_success(self):
        with self.assertRaises(ValueError):
            self.runtime.submit("alice", "tablet", {"tabId": 7, "steps": [{"op": "eval"}]})
        with self.assertRaises(PermissionError):
            self.runtime.submit("alice", "tablet", self.plan, allowed_devices=["other"])
        self.assertEqual(self.broker.commands, [])
        task = self.runtime.submit("alice", "tablet", self.plan, allowed_devices=["tablet"], scoped_client=True)
        result = self.await_done(task["taskId"])
        self.assertEqual(result["state"], "completed")
        self.assertEqual([c["op"] for c in self.broker.commands], ["acquire_lease", "fill", "click", "release_lease"])
        for command in self.broker.commands:
            self.assertEqual(command["_scopedClient"], "alice")
        self.assertNotIn("fixture", str(result))

    def test_cancel_stops_later_actions_and_capacity_is_bounded(self):
        self.broker.block = True
        first = self.runtime.submit("alice", "tablet", self.plan)
        self.assertTrue(self.broker.started.wait(1))
        second = self.runtime.submit("alice", "tablet", self.plan)
        with self.assertRaisesRegex(ValueError, "TASK_QUEUE_FULL"):
            self.runtime.submit("alice", "tablet", self.plan)
        self.runtime.cancel(first["taskId"], "alice")
        self.runtime.cancel(second["taskId"], "alice")
        self.broker.release.set()
        self.assertEqual(self.await_done(first["taskId"])["state"], "cancelled")
        self.assertEqual(self.await_done(second["taskId"])["state"], "cancelled")
        self.assertNotIn("click", [c["op"] for c in self.broker.commands])
        self.assertEqual(sum(c["op"] == "acquire_lease" for c in self.broker.commands), 1)
        self.assertEqual(self.broker.commands[-1]["op"], "release_lease")

    def test_explicit_output_fields_are_retained_and_owner_scoped(self):
        task = self.runtime.submit("alice", "tablet", {**self.plan, "outputFields": ["ok"]})
        identifier = task["taskId"]
        completed = self.await_done(identifier)
        self.assertTrue(completed["resultAvailable"])
        self.assertIn("artifactId", completed)
        self.assertNotIn("result", completed)
        self.assertEqual(self.runtime.get(identifier, "alice", include_result=True)["result"]["output"], {"ok": True})
        with self.assertRaises(KeyError):
            self.runtime.get(identifier, "bob", include_result=True)

    def test_requested_result_survives_restart(self):
        task = self.runtime.submit("alice", "tablet", self.plan, retain_result=True)
        identifier = task["taskId"]
        self.await_done(identifier)
        retained = self.runtime.get(identifier, "alice", include_result=True)
        self.assertEqual(retained["result"]["state"], "executed")
        self.assertIn("workflowId", retained["result"])
        self.assertNotIn("result", self.runtime.get(identifier, "alice"))
        self.runtime.close()
        path = self.store.path
        self.store.close()
        self.store = TaskStore(path)
        self.runtime = TaskRuntime(self.broker, self.store)
        self.assertEqual(self.runtime.get(identifier, "alice", include_result=True)["result"], retained["result"])

    def test_uncertain_command_is_never_replayed(self):
        self.broker.uncertain = True
        task = self.runtime.submit("alice", "tablet", self.plan)
        result = self.await_done(task["taskId"])
        self.assertEqual(result["state"], "unknown")
        self.assertTrue(result["receipt"]["actionMayHaveOccurred"])
        self.assertEqual(sum(c["op"] == "fill" for c in self.broker.commands), 1)
        self.assertNotIn("click", [c["op"] for c in self.broker.commands])

    def test_observations_do_not_generate_durable_identities(self):
        plan = {"tabId": 7, "steps": [{"op": "read", "args": {}}]}
        task = self.runtime.submit("alice", "tablet", plan)
        self.assertEqual(self.await_done(task["taskId"])["state"], "completed")
        read = next(c for c in self.broker.commands if c["op"] == "read")
        self.assertIsNone(read["actionId"])
        self.assertTrue(next(c for c in self.broker.commands if c["op"] == "acquire_lease")["actionId"])


if __name__ == "__main__":
    unittest.main()
