import concurrent.futures
import os
from pathlib import Path
import tempfile
import unittest
from client_auth import ClientCredentials


class ClientCredentialTests(unittest.TestCase):
    def test_memory_creation_scope_revocation_and_validation(self):
        store = ClientCredentials(max_clients=1)
        entry = store.register(["device-a", "device-a"])
        self.assertEqual(store.authenticate(entry["token"]), {"clientId": entry["clientId"], "devices": ["device-a"]})
        self.assertIsNone(store.authenticate(entry["token"] + "x"))
        self.assertIsNone(store.authenticate("admin-token"))
        with self.assertRaises(ValueError):
            store.register(["another"])
        self.assertTrue(store.revoke(entry["clientId"]))
        self.assertFalse(store.revoke(entry["clientId"]))
        self.assertIsNone(store.authenticate(entry["token"]))
        for devices in ([], ["*"], ["bad device"], "tablet", [None], ["a" * 129]):
            with self.assertRaises(ValueError):
                store.register(devices)
        with self.assertRaises(ValueError):
            store.revoke("../../../file")

    def test_persistent_private_atomic_cross_instance_updates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private" / "clients.json"
            first, second = ClientCredentials(path), ClientCredentials(path)
            record = first.register(["tablet"])
            self.assertEqual(second.authenticate(record["token"])["clientId"], record["clientId"])
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertNotIn(record["token"], path.read_text())
            self.assertNotIn("hash", str(first.list_clients()))
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                entries = list(pool.map(lambda _: ClientCredentials(path).register(["tablet"]), range(20)))
            self.assertEqual(len(first.list_clients()), 21)
            for entry in entries:
                self.assertIsNotNone(second.authenticate(entry["token"]))
            second.revoke(record["clientId"])
            self.assertIsNone(first.authenticate(record["token"]))
            self.assertEqual(list(path.parent.glob(".clients.json-*")), [])

    def test_corruption_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clients.json"
            store = ClientCredentials(path)
            record = store.register(["tablet"])
            path.write_text('{"version":1,"clients":{"bad":{}}}')
            with self.assertRaises(ValueError):
                store.authenticate(record["token"])
            with self.assertRaises(ValueError):
                store.register(["tablet"])


if __name__ == "__main__":
    unittest.main()
