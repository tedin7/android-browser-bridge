import os
from pathlib import Path
import tempfile
import unittest
from task_store import TaskStore


class TaskStoreTests(unittest.TestCase):
    def test_persistence_restart_and_cooperative_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tasks.sqlite"
            store = TaskStore(path)
            task = store.create("fill", "tablet", 7, "alice")
            task_id = task["taskId"]
            self.assertEqual(store.progress(task_id, .5, "alice")["progress"], .5)
            cancelled = store.cancel(task_id, "alice")
            self.assertEqual(cancelled["state"], "working")
            self.assertTrue(cancelled["cancelRequested"])
            with self.assertRaises(KeyError):
                store.get(task_id, "bob")
            with self.assertRaises(RuntimeError):
                TaskStore(path)
            store.close()
            store = TaskStore(path)
            self.assertEqual(store.get(task_id, "alice")["state"], "unknown")
            self.assertTrue(store.get(task_id, "alice")["receipt"]["actionMayHaveOccurred"])
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            store.close()

    def test_completed_history_does_not_consume_active_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = TaskStore(Path(temporary) / "tasks.sqlite", max_tasks=1, max_history=2)
            identifiers = []
            for _ in range(8):
                identifier = store.create("read", "tablet")["taskId"]
                store.finish(identifier, "completed", {"verified": True})
                identifiers.append(identifier)
            current = store.create("read", "tablet")["taskId"]
            self.assertEqual(store.get(current)["state"], "working")
            self.assertEqual(store._db.execute("SELECT count(*) FROM tasks WHERE state!='working'").fetchone()[0], 2)
            with self.assertRaises(KeyError):
                store.get(identifiers[0])
            with self.assertRaises(ValueError):
                store.create("read", "tablet")
            store.close()

    def test_artifact_total_budget_evicts_terminal_history_not_active_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = TaskStore(Path(temporary) / "tasks.sqlite", max_artifact_bytes=32, max_artifact_total_bytes=40)
            first = store.create("read", "tablet")["taskId"]
            old = store.save_artifact(first, "x" * 24)["artifactId"]
            store.finish(first, "completed")
            second = store.create("read", "tablet")["taskId"]
            store.save_artifact(second, "y" * 24)
            self.assertFalse((store.artifacts / old).exists())
            with self.assertRaises(KeyError):
                store.get(first)
            third = store.create("read", "tablet")["taskId"]
            with self.assertRaisesRegex(ValueError, "Active artifacts"):
                store.save_artifact(third, "z" * 24)
            self.assertEqual(store.read_artifact(second), "y" * 24)
            self.assertLessEqual(sum(path.stat().st_size for path in store.artifacts.iterdir()), 40)
            store.close()

    def test_receipts_artifacts_capacity_and_expiry(self):
        with tempfile.TemporaryDirectory() as temporary:
            now = [100.0]
            store = TaskStore(Path(temporary) / "tasks.sqlite", max_tasks=1, ttl_seconds=10, max_artifact_bytes=32, clock=lambda: now[0])
            task_id = store.create("read", "tablet")["taskId"]
            with self.assertRaises(ValueError):
                store.create("read", "tablet")
            with self.assertRaises(ValueError):
                store.finish(task_id, "completed", {"text": "page secret"})
            with self.assertRaises(ValueError):
                store.save_artifact(task_id, "x" * 100)
            artifact = store.save_artifact(task_id, {"text": "explicit"})
            self.assertEqual(os.stat(store.artifacts / artifact["artifactId"]).st_mode & 0o777, 0o600)
            self.assertEqual(store.read_artifact(task_id), {"text": "explicit"})
            store.cancel(task_id)
            result = store.finish(task_id, "completed", {"verified": True})
            self.assertEqual(result["state"], "completed")
            self.assertTrue(result["cancelRequested"])
            with self.assertRaises(ValueError):
                store.progress(task_id, 1)
            now[0] += 11
            with self.assertRaises(KeyError):
                store.get(task_id)
            self.assertFalse((store.artifacts / artifact["artifactId"]).exists())
            store.create("read", "tablet")
            store.close()


if __name__ == "__main__":
    unittest.main()
