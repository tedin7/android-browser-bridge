import copy
import unittest
from observation_cache import ObservationCache


class ObservationCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        self.cache = ObservationCache(clock=lambda: self.now)
        self.args = dict(client_id="client-a", device="tablet", tab_id=7,
                         region_args={"selector": "#panel", "textLimit": 2000})
        self.data = {"documentId": "doc-a", "text": "fixture " * 100,
                     "elements": [{"ref": "one", "enabled": False}],
                     "readyState": "complete", "textTruncated": True}

    def observe(self, data=None, **kwargs):
        return self.cache.observe(**{**self.args, **kwargs}, observation=self.data if data is None else data)

    def test_delta_reconstructs_exact_snapshot(self):
        first = self.observe()
        changed = copy.deepcopy(self.data)
        changed["elements"] = [{"ref": "two", "enabled": True}]
        del changed["textTruncated"]
        result = self.observe(changed, since_snapshot=first["snapshotId"])
        self.assertEqual(result["mode"], "delta")
        rebuilt = first["data"]
        rebuilt.update(result["changed"])
        for key in result["removed"]:
            rebuilt.pop(key)
        self.assertEqual(rebuilt, changed)
        self.assertEqual(result["documentId"], "doc-a")

    def test_scoping_expiry_navigation_and_revocation(self):
        first = self.observe()["snapshotId"]
        for overrides in ({"client_id": "client-b"}, {"device": "other"},
                          {"tab_id": 8}, {"region_args": {"selector": "#other"}}):
            self.assertEqual(self.observe(since_snapshot=first, **overrides)["mode"], "full")
        result = self.observe({**self.data, "documentId": "doc-b"}, since_snapshot=first)
        self.assertEqual(result["reason"], "document_changed")
        self.now += 121
        self.assertEqual(self.observe(since_snapshot=result["snapshotId"])["mode"], "full")
        self.cache.clear_client("client-a")
        self.assertGreaterEqual(self.cache.stats()["snapshots"], 0)
        self.assertEqual(self.observe(since_snapshot=first)["reason"], "snapshot_unavailable")

    def test_storage_is_bounded_and_unaliased(self):
        self.cache = ObservationCache(max_snapshots=1, max_bytes=2000)
        first = self.observe()
        first["data"]["text"] = "mutated returned object"
        result = self.observe(since_snapshot=first["snapshotId"])
        self.assertEqual(result["mode"], "delta")
        self.assertEqual(result["changed"], {})
        self.assertEqual(self.cache.stats()["snapshots"], 1)
        self.assertEqual(self.observe(since_snapshot=first["snapshotId"])["reason"], "snapshot_unavailable")
        result = self.observe({**self.data, "text": "x" * 10000})
        self.assertIsNone(result["snapshotId"])
        self.assertEqual(result["reason"], "observation_too_large")
        self.assertLessEqual(self.cache.stats()["bytes"], 2000)

    def test_missing_document_and_bad_inputs(self):
        self.assertEqual(self.observe({"text": "loading"})["reason"], "document_unavailable")
        for overrides in ({"tab_id": True}, {"client_id": ""}, {"since_snapshot": {}},
                          {"region_args": {"limit": float("nan")}}):
            with self.assertRaises(ValueError):
                self.observe(**overrides)


if __name__ == "__main__":
    unittest.main()
