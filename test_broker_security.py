"""Local synthetic-credential regressions for admission, recovery and sharing."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from action_store import ActionStore
from bridge import Broker, make_server, api


class BrokerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0, 'test-admin-credential')
        self.broker = self.server.broker
        self.broker.credentials['fixture'] = 'test-device-credential'
        self.broker.handle('/api/poll', {'device': 'fixture'})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.owner = self.broker.clients.register(['fixture'])
        self.other = self.broker.clients.register(['fixture'])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.broker.action_store.close()
        if self.broker._artifact_temporary:
            self.broker._artifact_temporary.cleanup()

    def request(self, path, data, token=None):
        token = token or self.owner['token']
        request = Request(self.origin+path, data=json.dumps(data).encode(), headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def command(self, identity='action_test_00000001', **extra):
        status, result = self.request('/api/command', {'device': 'fixture', 'op': 'read', 'args': {}, 'actionId': identity, **extra})
        self.assertEqual(status, 200)
        return result['id']

    def test_wire_principals_cannot_change_command_ownership(self):
        identifier = self.command(_client=self.other['clientId'], _scopedClient=self.other['clientId'])
        self.assertEqual(self.broker.commands[identifier]['client'], self.owner['clientId'])
        status, _ = self.request('/api/status', {'id': identifier, '_scopedClient': self.owner['clientId']}, self.other['token'])
        self.assertEqual(status, 403)
        status, _ = self.request('/api/action-status', {'actionId': 'action_test_00000001', '_client': self.owner['clientId']}, self.other['token'])
        self.assertEqual(status, 404)

    def test_revoke_cancels_queued_and_journals_nonexecution(self):
        identifier = self.command()
        status, result = self.request('/api/clients/revoke', {'clientId': self.owner['clientId']}, 'test-admin-credential')
        self.assertEqual(status, 200)
        self.assertTrue(result['revoked'])
        status, polled = self.request('/api/poll', {'device': 'fixture'}, 'test-device-credential')
        self.assertEqual(status, 200)
        self.assertIsNone(polled['command'])
        self.assertEqual(self.broker.commands[identifier]['state'], 'expired')
        self.assertEqual(self.broker.action_store.lookup(self.owner['clientId'], 'action_test_00000001')['state'], 'not_executed')
        self.assertEqual(self.request('/api/status', {'id': identifier})[0], 401)

    def test_external_credential_revocation_rechecked_before_dispatch(self):
        self.command()
        self.broker.clients.revoke(self.owner['clientId'])
        self.assertIsNone(self.broker.handle('/api/poll', {'device': 'fixture'})['command'])
        self.assertEqual(self.broker.action_store.lookup(self.owner['clientId'], 'action_test_00000001')['state'], 'not_executed')

    def test_device_revocation_preserves_uncertainty_for_dispatched(self):
        first = self.command()
        self.broker.handle('/api/poll', {'device': 'fixture'})
        self.command('action_test_00000002')
        self.broker.handle('/api/revoke', {'device': 'fixture'})
        self.assertEqual(self.broker.commands[first]['state'], 'expired')
        self.assertEqual(self.broker.action_store.lookup(self.owner['clientId'], 'action_test_00000001')['state'], 'unknown')
        self.assertEqual(self.broker.action_store.lookup(self.owner['clientId'], 'action_test_00000002')['state'], 'not_executed')

    def test_native_share_requires_device_credential_and_bounds_identity(self):
        payload = {'device': 'fixture', 'shareId': 'share_test_00000001', 'text': 'owned fixture text'}
        self.assertEqual(self.request('/api/native-share', payload)[0], 401)
        status, result = self.request('/api/native-share', payload, 'test-device-credential')
        self.assertEqual(status, 200)
        self.assertEqual(set(result), {'artifactId', 'size'})
        path = self.broker.artifacts.directory / (result['artifactId']+'.bin')
        self.assertEqual(path.read_text(), 'owned fixture text')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.broker.handle('/api/revoke', {'device': 'fixture'})
        self.assertEqual(self.request('/api/native-share', payload, 'test-device-credential')[0], 401)


class DurableStateTests(unittest.TestCase):
    def test_expired_lookup_not_confused_with_conflicting_live_identity(self):
        store = ActionStore(ttl=1)
        with patch('action_store.time.time', return_value=10):
            store.reserve('client', 'identity', 'old', 'command')
        with patch('action_store.time.time', return_value=12):
            self.assertIsNone(store.lookup('client', 'identity', 'new'))
            store.reserve('client', 'identity', 'new', 'fresh')
            self.assertEqual(store.lookup('client', 'identity')['id'], 'fresh')
        store.close()

    def test_queue_and_dispatched_expiry_journal_survive_detail_eviction(self):
        broker = Broker(history_ttl=60)
        broker.handle('/api/poll', {'device': 'fixture'})
        first = broker.handle('/api/command', {'device': 'fixture', 'op': 'read', 'actionId': 'action_test_00000001'})['id']
        broker.commands[first]['created'] = time.time()-31
        broker.handle('/api/status', {'id': first})
        self.assertEqual(broker.action_store.lookup('local-admin', 'action_test_00000001')['state'], 'not_executed')
        second = broker.handle('/api/command', {'device': 'fixture', 'op': 'read', 'actionId': 'action_test_00000002'})['id']
        broker.handle('/api/poll', {'device': 'fixture'})
        broker.commands[second]['created'] = time.time()-61
        with broker.changed:
            broker.prune_history(time.time())
        self.assertEqual(broker.action_store.lookup('local-admin', 'action_test_00000002')['state'], 'unknown')
        broker.action_store.close()

    def test_restart_reconciliation_does_not_enqueue_again(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'devices.json'
            broker = Broker(path)
            broker.handle('/api/poll', {'device': 'fixture'})
            request = {'device': 'fixture', 'op': 'read', 'actionId': 'action_test_00000001', 'args': {}}
            original = broker.handle('/api/command', request)
            broker.handle('/api/poll', {'device': 'fixture'})
            broker.action_store.close()
            restored = Broker(path)
            duplicate = restored.handle('/api/command', request)
            self.assertEqual(duplicate['id'], original['id'])
            self.assertEqual(duplicate['state'], 'unknown')
            self.assertEqual(len(restored.commands), 0)
            self.assertEqual(sum(map(len, restored.queues.values())), 0)
            restored.action_store.close()

    def test_explicit_http_timeout_is_honored(self):
        with patch('bridge.http.client.HTTPConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{}'
            self.assertEqual(api('http://unique-timeout-fixture:9871', 'test', '/api/status', {}, timeout=.125), {})
            self.assertEqual(connection.call_args.kwargs['timeout'], .125)
        for value in (True, 0, -1, 66, float('nan')):
            with self.assertRaises(ValueError):
                api('http://localhost', 'test', '/api/status', {}, timeout=value)


if __name__ == '__main__':
    unittest.main()
