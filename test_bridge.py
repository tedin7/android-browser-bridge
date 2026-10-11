import unittest
import tempfile
import threading
import urllib.error
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from bridge import Broker, api, make_server
from mcp_server import handle
from launcher import validate_origin


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.broker = Broker()

    def test_offline_rejected(self):
        with self.assertRaisesRegex(ValueError, "offline"):
            self.broker.handle("/api/command", {"device": "tablet", "op": "tabs"})

    def test_lifecycle_and_no_replay(self):
        self.broker.handle("/api/poll", {"device": "tablet"})
        identifier = self.broker.handle("/api/command", {"device": "tablet", "op": "read"})["id"]
        self.assertIsNone(self.broker.handle("/api/poll", {"device": "other"})["command"])
        command = self.broker.handle("/api/poll", {"device": "tablet"})["command"]
        self.assertEqual(command["id"], identifier)
        self.assertIsNone(self.broker.handle("/api/poll", {"device": "tablet"})["command"])
        with self.assertRaises(ValueError):
            self.broker.handle("/api/result", {"device": "other", "id": identifier})
        self.broker.handle("/api/result", {"device": "tablet", "id": identifier, "result": {"title": "Test"}})
        self.broker.handle("/api/result", {"device": "tablet", "id": identifier, "result": {"title": "Duplicate"}})
        self.assertEqual(self.broker.handle("/api/status", {"id": identifier})["result"], {"title": "Test"})

    def test_no_arbitrary_scripts(self):
        self.broker.handle("/api/poll", {"device": "tablet"})
        with self.assertRaises(ValueError):
            self.broker.handle("/api/command", {"device": "tablet", "op": "eval", "args": {}})

    def test_stale_command_expires(self):
        self.broker.handle("/api/poll", {"device": "tablet"})
        identifier = self.broker.handle("/api/command", {"device": "tablet", "op": "click"})["id"]
        self.broker.commands[identifier]["created"] -= 31
        self.assertIsNone(self.broker.handle("/api/poll", {"device": "tablet"})["command"])
        self.assertEqual(self.broker.handle("/api/status", {"id": identifier})["state"], "expired")

    def test_mcp_discovery(self):
        initialized = handle({"method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(initialized["protocolVersion"], "2025-03-26")
        self.assertEqual(len(handle({"method": "tools/list"})["tools"]), 5)

    def test_pair_once_and_revoke(self):
        code = self.broker.handle("/api/enroll", {"device": "tablet"})["code"]
        paired = self.broker.pair(code)
        self.assertTrue(self.broker.authorized_device("tablet", paired["token"]))
        self.assertFalse(self.broker.authorized_device("other", paired["token"]))
        with self.assertRaises(ValueError):
            self.broker.pair(code)
        self.broker.handle("/api/revoke", {"device": "tablet"})
        self.assertFalse(self.broker.authorized_device("tablet", paired["token"]))

    def test_old_poll_cannot_dispatch_after_repair(self):
        code=self.broker.handle('/api/enroll',{'device':'tablet'})['code']
        old=self.broker.pair(code)['token']
        with ThreadPoolExecutor(max_workers=1) as workers:
            pending=workers.submit(self.broker.handle,'/api/poll',{'device':'tablet','_credential':old,'waitMs':2000})
            deadline=time.monotonic()+1
            while 'tablet' not in self.broker.leases and time.monotonic()<deadline: time.sleep(.001)
            self.broker.handle('/api/revoke',{'device':'tablet'})
            code=self.broker.handle('/api/enroll',{'device':'tablet'})['code']
            current=self.broker.pair(code)['token']
            self.broker.handle('/api/poll',{'device':'tablet','_credential':current})
            identifier=self.broker.handle('/api/command',{'device':'tablet','op':'tabs'})['id']
            try: self.assertIsNone(pending.result(timeout=1)['command'])
            except ValueError: pass
            self.assertEqual(self.broker.handle('/api/poll',{'device':'tablet','_credential':current})['command']['id'],identifier)
            with self.assertRaises(ValueError): self.broker.handle('/api/result',{'device':'tablet','_credential':old,'id':identifier,'result':{}})

    def test_pairing_expiry(self):
        code = self.broker.handle("/api/enroll", {"device": "tablet"})["code"]
        self.broker.pairings[code]["expires"] = 0
        with self.assertRaises(ValueError):
            self.broker.pair(code)

    def test_credentials_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            broker = Broker(path)
            code = broker.handle("/api/enroll", {"device": "tablet"})["code"]
            paired = broker.pair(code)
            self.assertTrue(Broker(path).authorized_device("tablet", paired["token"]))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_connection_policy(self):
        for origin in ("http://192.168.1.10:8766", "http://10.0.1.2:8766", "https://server.example:8766", "http://[::1]:8766"):
            self.assertEqual(validate_origin(origin), origin)
        for origin in ("http://8.8.8.8:8766", "javascript:alert(1)", "https://user:pass@server.example", "https://server.example/path"):
            with self.assertRaises(ValueError):
                validate_origin(origin)

    def test_event_driven_dispatch_and_result_without_sleep_polling(self):
        self.broker.handle('/api/poll',{'device':'tablet'})
        with ThreadPoolExecutor(max_workers=2) as workers:
            poll=workers.submit(self.broker.handle,'/api/poll',{'device':'tablet','waitMs':2000})
            execute=workers.submit(self.broker.handle,'/api/execute',{'device':'tablet','op':'tabs','waitMs':2000})
            command=poll.result(timeout=1)['command']
            self.broker.handle('/api/result',{'device':'tablet','id':command['id'],'result':[{'id':1}],'durationMs':2})
            response=execute.result(timeout=1)
            self.assertEqual(response['result'],[{'id':1}])
            self.assertEqual(response['state'],'done')
            self.assertLess(response['timing']['totalMs'],1000)

    def test_long_poll_preserves_online_lease(self):
        now=time.time()
        self.broker.devices['tablet']=now-20
        self.broker.leases['tablet']=now+5
        self.assertTrue(self.broker.handle('/api/devices',{})['devices'][0]['online'])
        self.broker.handle('/api/command',{'device':'tablet','op':'tabs'})

    def test_revoke_wakes_waiting_execute(self):
        self.broker.handle('/api/poll',{'device':'tablet'})
        with ThreadPoolExecutor(max_workers=1) as workers:
            waiting=workers.submit(self.broker.handle,'/api/execute',{'device':'tablet','op':'tabs','waitMs':2000})
            deadline=time.monotonic()+1
            while not self.broker.commands and time.monotonic()<deadline: time.sleep(.001)
            self.broker.handle('/api/revoke',{'device':'tablet'})
            self.assertEqual(waiting.result(timeout=1)['state'],'expired')


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0, "a" * 43)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_real_authenticated_round_trip_and_device_isolation(self):
        with self.assertRaisesRegex(RuntimeError, "Unauthorized"):
            api(self.url, "wrong", "/api/devices", {})
        code = api(self.url, "a" * 43, "/api/enroll", {"device": "tablet"})["code"]
        device_token = api(self.url, "", "/api/pair", {"code": code})["token"]
        with self.assertRaisesRegex(RuntimeError, "Unauthorized"):
            api(self.url, device_token, "/api/devices", {})
        with self.assertRaisesRegex(RuntimeError, "Unauthorized"):
            api(self.url, device_token, "/api/poll", {"device": "other"})
        with self.assertRaisesRegex(RuntimeError, "Unauthorized"):
            api(self.url, "a" * 43, "/api/poll", {"device": "tablet"})
        api(self.url, device_token, "/api/poll", {"device": "tablet"})
        command_id = api(self.url, "a" * 43, "/api/command", {"device": "tablet", "op": "tabs"})["id"]
        command = api(self.url, device_token, "/api/poll", {"device": "tablet"})["command"]
        self.assertEqual(command["id"], command_id)
        api(self.url, device_token, "/api/result", {"device": "tablet", "id": command_id, "result": [{"id": 7}]})
        self.assertEqual(api(self.url, "a" * 43, "/api/status", {"id": command_id})["result"], [{"id": 7}])
        api(self.url, "a" * 43, "/api/revoke", {"device": "tablet"})
        with self.assertRaisesRegex(RuntimeError, "Unauthorized"):
            api(self.url, device_token, "/api/poll", {"device": "tablet"})


if __name__ == "__main__":
    unittest.main()
