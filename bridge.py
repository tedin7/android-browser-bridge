#!/usr/bin/env python3
"""Authenticated, loopback-only command broker and CLI. Python standard library."""
import argparse
import hmac
import json
import os
import re
import secrets
import socket
import sys
import threading
import tempfile
import time
import http.client
from urllib.parse import urlsplit
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from operation_registry import OPERATIONS, PRODUCT_VERSION, validate_arguments

# The Android companion has its own fixed contract; the Firefox catalog stays unchanged.
NATIVE_OPERATIONS = frozenset({'capabilities', 'read', 'locate', 'inspect', 'click', 'fill', 'back', 'scroll', 'foreground', 'press'})
NATIVE_ARGUMENTS = {'package': str, 'key': str, 'ref': str, 'name': str, 'label': str, 'role': str, 'textQuery': str, 'exact': bool,
    'value': str, 'force': bool, 'y': (int, float), 'textLimit': int, 'maxElements': int, 'selectors': bool, 'responseFields': list}
NATIVE_PACKAGE = re.compile(r'[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+')


def validate_native_arguments(operation, args):
    if operation not in NATIVE_OPERATIONS:
        raise ValueError('UNSUPPORTED_OPERATION: The native companion supports ' + ', '.join(sorted(NATIVE_OPERATIONS)))
    for key, value in args.items():
        kind = NATIVE_ARGUMENTS.get(key)
        if kind is None or isinstance(value, bool) != (kind is bool) or not isinstance(value, kind):
            raise ValueError('INVALID_ARGUMENT: ' + key + ' is not a native companion argument of the expected type')
    if 'package' in args and (len(args['package']) > 255 or not NATIVE_PACKAGE.fullmatch(args['package'])):
        raise ValueError('INVALID_ARGUMENT: package must be an exact Android package name')
    if isinstance(args.get('value'), str) and len(args['value']) > 10000:
        raise ValueError('INVALID_ARGUMENT: value exceeds 10000 characters')
from action_store import ActionStore, ActionCapacityError, needs_durable_identity
from client_auth import ClientCredentials

ROOT = Path(__file__).resolve().parent

class BrokerError(ValueError):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code, self.status = code, status
        self.details = details or {}


def response_arguments(arguments):
    """Recovery formatting hints only: never return form values or selectors."""
    result = {k: arguments[k] for k in ('selectors', 'textLimit', 'maxElements') if k in arguments}
    if isinstance(arguments.get('steps'), list):
        result['steps'] = [{'op': step.get('op'), 'args': response_arguments(step.get('args', {}))}
                           for step in arguments['steps'] if isinstance(step, dict)]
    return result



def token_file(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_urlsafe(32) + "\n")
    value = path.read_text().strip()
    if len(value) < 32:
        raise ValueError("Token must be at least 32 characters")
    return value


class Broker:
    def __init__(self, credentials_file=None, *, active_limit=256, client_limit=32,
                 history_limit=1000, history_bytes=64*1024*1024, history_ttl=600,
                 action_limit=10000, action_client_limit=None, action_ttl=86400):
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.queues = defaultdict(deque)
        self.samples = defaultdict(lambda: deque(maxlen=512))
        self.device_info = {}
        self.leases = {}
        self.last_cleanup = 0.0
        self.devices = {}
        self.commands = {}
        self.active_limit, self.client_limit = active_limit, client_limit
        self.history_limit, self.history_bytes, self.history_ttl = history_limit, history_bytes, history_ttl
        self.pairings = {}
        self.artifacts = None
        self._artifact_temporary = None
        self.task_runtime = None
        self._task_temporary = None
        self.credentials_file = Path(credentials_file) if credentials_file else None
        self.action_store = ActionStore(self.credentials_file.with_suffix('.actions.sqlite') if self.credentials_file else None, ttl=action_ttl, limit=action_limit, client_limit=action_client_limit)
        self.clients = ClientCredentials(self.credentials_file.with_suffix('.clients.json') if self.credentials_file else None)
        self.credentials = json.loads(self.credentials_file.read_text()) if self.credentials_file and self.credentials_file.exists() else {}
        self.devices.update({device: 0 for device in self.credentials})

    @staticmethod
    def wait_ms(data, maximum=40000):
        value=data.get('waitMs',0)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0 <= value <= maximum:
            raise ValueError('waitMs outside allowed range')
        return value / 1000

    def command_status(self, command):
        result={"id":command["id"],"state":command["state"]}
        result.update(operation=command['op'], responseArgs=response_arguments(command.get('args', {})))
        if command.get('actionId'): result['actionId'] = command['actionId']
        for key in ("result","error","timing"):
            if key in command: result[key]=command[key]
        return result

    def prune_history(self, now):
        history = []
        for identifier, command in list(self.commands.items()):
            self.expire_queued(command)
            if command['state'] == 'dispatched' and now-command['created'] > self.history_ttl:
                self.action_store.update(command['id'], 'unknown')
                command.update(state='expired', error='Command outcome unknown after retention deadline')
                self.changed.notify_all()
            if command['state'] not in ('queued', 'dispatched'):
                size = command.get('_retainedBytes')
                if size is None:
                    size = len(json.dumps(command, ensure_ascii=False, separators=(',', ':')).encode())
                    command['_retainedBytes'] = size
                history.append((command.get('finishedAt', command['created']), identifier, size))
        history.sort()
        count, size = len(history), sum(item[2] for item in history)
        for finished, identifier, item_size in history:
            if now-finished > self.history_ttl or count > self.history_limit or size > self.history_bytes:
                del self.commands[identifier]
                count -= 1
                size -= item_size

    def expire_queued(self, command):
        if command['state']=='queued' and time.time()-command['created'] > 30:
            self.action_store.update(command['id'], 'not_executed')
            command.update(state='expired',error='Browser did not pick up command within 30 seconds')
            self.changed.notify_all()

    def save_native_share(self, device, data):
        with self.changed:
            expected = self.credentials.get(device, '')
            supplied = data.get('_credential', '')
            if not expected or not hmac.compare_digest(expected, supplied):
                raise BrokerError('DEVICE_REVOKED', 'Device must be paired to share', 401)
            if self.artifacts is None:
                from native_artifacts import NativeArtifacts
                if self.credentials_file:
                    directory = self.credentials_file.parent / 'artifacts'
                else:
                    self._artifact_temporary = tempfile.TemporaryDirectory(prefix='browser-bridge-artifacts-')
                    directory = self._artifact_temporary.name
                self.artifacts = NativeArtifacts(directory)
            return self.artifacts.save(device, data)

    def get_native_artifact(self, data):
        with self.changed:
            if self.artifacts is None:
                from native_artifacts import NativeArtifacts
                if self.credentials_file:
                    directory = self.credentials_file.parent / 'artifacts'
                else:
                    self._artifact_temporary = tempfile.TemporaryDirectory(prefix='browser-bridge-artifacts-')
                    directory = self._artifact_temporary.name
                self.artifacts = NativeArtifacts(directory)
            artifacts = self.artifacts
        try:
            return artifacts.get(data.get('artifactId'), data.get('device'), data.get('_devices'))
        except PermissionError:
            raise BrokerError('FORBIDDEN', 'Artifact device outside client scope', 403) from None
        except KeyError:
            raise BrokerError('ARTIFACT_UNAVAILABLE', 'Artifact expired or unavailable', 404) from None

    def revoke_client(self, identifier):
        # Admission and dispatch share this lock; a revoked queued action cannot
        # slip through between credential removal and queue cancellation.
        with self.changed:
            revoked = self.clients.revoke(identifier)
            for command in self.commands.values():
                if command.get('client') == identifier and command['state'] == 'queued':
                    self.action_store.update(command['id'], 'not_executed')
                    command.update(state='expired', error='Client revoked before dispatch')
            self.changed.notify_all()
            return revoked

    def wait_result(self, identifier, seconds, client=None):
        deadline=time.monotonic()+seconds
        with self.changed:
            while True:
                command=self.commands.get(identifier)
                if command is None: raise ValueError('Unknown or expired command')
                if client is not None and command.get('client') != client:
                    raise BrokerError('FORBIDDEN','Command belongs to another client',403)
                self.expire_queued(command)
                remaining=deadline-time.monotonic()
                if command['state'] in ('done','expired') or remaining<=0:
                    return self.command_status(command)
                if command['state']=='queued': remaining=min(remaining,max(.01,30-(time.time()-command['created'])))
                self.changed.wait(remaining)

    def save_credentials(self):
        if self.credentials_file:
            self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.credentials_file.with_suffix(".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(self.credentials, stream)
            temporary.replace(self.credentials_file)

    def authorized_device(self, device, token):
        with self.lock:
            expected = self.credentials.get(device)
            return isinstance(token, str) and expected is not None and hmac.compare_digest(token.encode(), expected.encode())

    def pair(self, code):
        with self.lock:
            enrollment = self.pairings.get(code) if isinstance(code, str) else None
            if not enrollment or enrollment["expires"] < time.time():
                raise ValueError("Invalid or expired pairing code")
            del self.pairings[code]
            device = enrollment["device"]
            token = secrets.token_urlsafe(32)
            self.credentials[device] = token
            self.devices[device] = 0
            self.save_credentials()
            return {"device": device, "token": token}

    def handle(self, path, data):
        if path == '/api/native-artifacts/get':
            return self.get_native_artifact(data)
        if path in {'/api/tasks/start','/api/tasks/get','/api/tasks/cancel','/api/native-artifacts/get'}:
            with self.changed:
                if self.task_runtime is None:
                    from task_runtime import TaskRuntime
                    from task_store import TaskStore
                    if self.credentials_file:
                        task_path=self.credentials_file.with_suffix('.tasks.sqlite')
                    else:
                        self._task_temporary=tempfile.TemporaryDirectory(prefix='browser-tasks-')
                        task_path=Path(self._task_temporary.name)/'tasks.sqlite'
                    self.task_runtime=TaskRuntime(self,TaskStore(task_path))
                runtime=self.task_runtime
            client=data.get('_client','local-admin')
            if path == '/api/tasks/start':
                return runtime.submit(client,data['device'],data['plan'],allowed_devices=data.get('_devices'),scoped_client=bool(data.get('_scopedClient')),retain_result=data.get('retainResult') is True)
            if path == '/api/tasks/get':return runtime.get(data['taskId'],client,include_result=data.get('includeResult') is True)
            return runtime.cancel(data['taskId'],client)
        if path == '/api/execute':
            seconds=self.wait_ms(data) if 'waitMs' in data else 40
            accepted=self.handle('/api/command',data)
            if accepted['id'] not in self.commands:
                return {**accepted, 'state':'unknown', 'error':'ACTION_UNCERTAIN: retained identity exists but detailed result is unavailable; do not repeat'}
            identifier=accepted['id']
            return self.wait_result(identifier,seconds,data.get('_scopedClient'))
        if path == '/api/action-status':
            with self.changed:
                identity = self.action_store.lookup(data.get('_client','local-admin'),data.get('actionId'))
                if identity is None: raise BrokerError('ACTION_NOT_FOUND', 'Action identity is not retained',404)
                command=self.commands.get(identity['id'])
                return self.command_status(command) if command else {**identity,'resultAvailable':False}
        if path == '/api/status':
            return self.wait_result(data.get('id'),self.wait_ms(data),data.get('_scopedClient'))
        now = time.time()
        with self.changed:
            if now-self.last_cleanup >= 10:
                self.last_cleanup=now
                for code in list(self.pairings):
                    if self.pairings[code]['expires'] < now: del self.pairings[code]
                self.prune_history(now)
            if path == "/api/devices":
                return {"devices": [{"id": key, "lastSeen": seen, "online": now < self.leases.get(key,seen+15)}
                                    | self.device_info.get(key,{})
                                    for key, seen in self.devices.items()]}
            if path == '/api/metrics':
                output={}
                for op,records in self.samples.items():
                    values=sorted(record['totalMs'] for record in records)
                    output[op]={'count':len(values),'medianMs':round(values[len(values)//2],2),
                        'p95Ms':round(values[min(len(values)-1,int(len(values)*.95))],2),
                        'queueMedianMs':round(sorted(record['queueMs'] for record in records)[len(values)//2],2)}
                return {'actionJournal':self.action_store.stats(data.get('_client','local-admin')),'operations':output,'pending':sum(c['state'] in ('queued','dispatched') for c in self.commands.values())}
            device = data.get("device", "")
            if not isinstance(device, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", device):
                raise ValueError("Invalid device name")
            if path == "/api/enroll":
                if device in self.credentials or any(item["device"] == device for item in self.pairings.values()):
                    raise ValueError("Device already paired or awaiting pairing; revoke it first")
                code = "-".join(secrets.token_hex(3).upper() for _ in range(2))
                self.pairings[code] = {"device": device, "expires": now + 300}
                return {"device": device, "code": code, "expiresIn": 300}
            if path == "/api/revoke":
                self.credentials.pop(device, None)
                self.devices.pop(device, None)
                self.leases.pop(device,None)
                self.device_info.pop(device,None)
                self.queues.pop(device,None)
                self.pairings = {code: item for code, item in self.pairings.items() if item["device"] != device}
                for command in self.commands.values():
                    if command["device"] == device and command["state"] in ("queued", "dispatched"):
                        self.action_store.update(command['id'], 'not_executed' if command['state']=='queued' else 'unknown')
                        command.update(state="expired", error="Device revoked")
                self.save_credentials()
                self.changed.notify_all()
                return {"ok": True}
            if path == "/api/native-preflight":
                supplied = data.get('_credential', '')
                expected = self.credentials.get(device, '')
                if not expected or not supplied or not hmac.compare_digest(expected, supplied):
                    raise BrokerError('UNAUTHORIZED', 'Device authorization is no longer valid', 401)
                identifier = data.get('id')
                if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
                    raise BrokerError('INVALID_INPUT', 'A native command identifier is required', 400)
                command = self.commands.get(identifier)
                if not command or command['device'] != device or command['state'] != 'dispatched':
                    raise BrokerError('COMMAND_NOT_AUTHORIZED', 'The native command is no longer authorized for this device', 403)
                if command.get('scopedClient') and command['client'] not in {entry['clientId'] for entry in self.clients.list_clients()}:
                    raise BrokerError('COMMAND_NOT_AUTHORIZED', 'The originating client has been revoked', 403)
                return {'allowed': True}
            if path == "/api/poll":
                if data.get("_credential") is not None:
                    expected=self.credentials.get(device, "")
                    if not expected or not hmac.compare_digest(expected, data["_credential"]):
                        raise ValueError("Device revoked; pair again")
                self.devices[device] = now
                if isinstance(data.get('version'),str): self.device_info[device]={'version':data['version'][:32]}
                seconds=self.wait_ms(data,20000)
                self.leases[device]=now+seconds+15
                was_paired=device in self.credentials
                deadline=time.monotonic()+seconds
                while True:
                    if data.get('_credential') is not None:
                        expected=self.credentials.get(device,'')
                        if not expected or not hmac.compare_digest(expected,data['_credential']):
                            raise ValueError('Device revoked; pair again')
                    queue=self.queues[device]
                    while queue:
                        command=self.commands.get(queue.popleft())
                        if command is None: continue
                        self.expire_queued(command)
                        if command['state']!='queued': continue
                        if command.get('scopedClient') and command['client'] not in {entry['clientId'] for entry in self.clients.list_clients()}:
                            self.action_store.update(command['id'], 'not_executed')
                            command.update(state='expired', error='Client revoked before dispatch')
                            self.changed.notify_all()
                            continue
                        command['state']='dispatched'
                        self.action_store.update(command['id'], 'dispatched')
                        command['dispatchedAt']=time.perf_counter()
                        return {'command':{key:command[key] for key in ('id','op','args')}}
                    remaining=deadline-time.monotonic()
                    if remaining<=0: return {'command':None}
                    self.changed.wait(remaining)
                    if was_paired and device not in self.credentials:
                        return {'command':None}
                    self.devices[device]=time.time()
            if path == "/api/command":
                if data.get("op") not in OPERATIONS or not isinstance(data.get("args", {}), dict):
                    raise ValueError("Invalid operation or arguments")
                client = data.get('_client', 'local-admin')
                if data.get('_scopedClient') and client not in {entry['clientId'] for entry in self.clients.list_clients()}:
                    raise BrokerError('CLIENT_REVOKED', 'Client revoked before admission', 401)
                action_id = data.get('actionId')
                if action_id is not None:
                    if not isinstance(action_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,128}',action_id):
                        raise ValueError('Invalid actionId')
                    digest = self.action_store.fingerprint(device,data['op'],data.get('args',{}))
                    identity = self.action_store.lookup(client,action_id,digest)
                    if identity is not None:return identity
                if now >= self.leases.get(device,self.devices.get(device,0)+15):
                    raise ValueError("Device offline; open Firefox and enable the extension")
                if str(self.device_info.get(device, {}).get('version', '')).startswith('companion-'):
                    validate_native_arguments(data['op'], data.get('args', {}))
                else:
                    try:
                        validate_arguments(data['op'], data.get('args', {}))
                    except ValueError as error:
                        # Rejected before queueing: nothing reached the browser.
                        raise BrokerError('INVALID_ARGUMENT', str(error), 400) from None
                active = [c for c in self.commands.values() if c['state'] in ('queued', 'dispatched')]
                # _client is set by the authenticated HTTP handler, never trusted from the wire.
                client = data.get('_client', 'local-admin')
                if len(active) >= self.active_limit or sum(c.get('client', 'local-admin') == client for c in active) >= self.client_limit:
                    raise BrokerError('QUEUE_FULL', 'Active command limit reached', 429)
                identifier = secrets.token_urlsafe(16)
                if action_id is not None:
                    try:
                        self.action_store.reserve(client,action_id,digest,identifier)
                    except ActionCapacityError as error:
                        raise BrokerError('ACTION_CAPACITY', str(error), 429, error.details) from None
                self.commands[identifier] = {"id": identifier, "device": device, "op": data["op"],
                    "args": data.get("args", {}), "actionId":action_id, "client":client, "scopedClient":bool(data.get("_scopedClient")), "created": now, "state": "queued",'startedAt':time.perf_counter()}
                self.queues[device].append(identifier)
                self.changed.notify_all()
                return {"id": identifier}
            if path == "/api/result":
                if data.get("_credential") is not None:
                    expected=self.credentials.get(device, "")
                    if not expected or not hmac.compare_digest(expected, data["_credential"]):
                        raise BrokerError('DEVICE_REVOKED', "Device revoked; pair again", 401)
                command = self.commands.get(data.get("id"))
                if command is None or command.get('state') == 'expired':
                    raise BrokerError('COMMAND_EXPIRED', 'Command result is no longer retained', 410)
                if command["device"] != device or command["state"] not in ("dispatched", "done"):
                    raise BrokerError('RESULT_REJECTED', "Invalid result", 409)
                if command["state"] == "dispatched":
                    command["state"] = "done"
                    self.action_store.update(command['id'], 'executed' if 'error' not in data else 'failed')
                    command['finishedAt'] = now
                    if "error" in data:
                        command["error"] = str(data["error"])[:1000]
                    else:
                        command["result"] = data.get("result")
                    reported=time.perf_counter()
                    timing={'totalMs':round((reported-command['startedAt'])*1000,3),
                        'queueMs':round((command['dispatchedAt']-command['startedAt'])*1000,3),
                        'browserMs':data.get('durationMs')}
                    command['timing']=timing
                    self.samples[command['op']].append(timing)
                    self.changed.notify_all()
                    self.prune_history(now)
                return {"ok": True}
            raise ValueError("Unknown endpoint")


def make_server(port, token, credentials_file=None, host="127.0.0.1"):
    broker = Broker(credentials_file)

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def setup(self):
            super().setup()
            self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        def log_message(self, *_):
            pass

        def reply(self, status, value):
            payload = json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"ok": True, "version": PRODUCT_VERSION})
            fixture_path=urlsplit(self.path).path
            if fixture_path in {'/fixture','/frame'}:
                file=ROOT/('test_page.html' if fixture_path=='/fixture' else 'test_frame.html')
                if not file.is_file():return self.reply(404,{'error':'Fixture is not packaged'})
                payload=file.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers()
                return self.wfile.write(payload)
            if self.path in ("/", "/extension.xpi"):
                file = ROOT / ("install.html" if self.path == "/" else "android-browser-bridge.xpi")
                if not file.exists():
                    return self.reply(404, {"error": "Package not built"})
                payload = file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8" if self.path == "/" else "application/x-xpinstall")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                return self.wfile.write(payload)
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            self.connection.settimeout(10)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8_000_000:
                    raise ValueError("Invalid body size")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("JSON object required")
                if self.path == "/api/pair":
                    result = broker.pair(data.get("code"))
                else:
                    auth = self.headers.get("Authorization", "")
                    # Internal principal fields must never be accepted from HTTP input.
                    for key in list(data):
                        if key.startswith('_'):del data[key]
                    is_admin = hmac.compare_digest(auth.encode(), ("Bearer " + token).encode())
                    principal = None
                    if self.path in ("/api/poll", "/api/result", "/api/native-share", "/api/native-preflight"):
                        authorized = broker.authorized_device(data.get("device", ""), auth.removeprefix("Bearer "))
                        if authorized: data['_credential']=auth.removeprefix('Bearer ')
                    else:
                        principal = None if is_admin else broker.clients.authenticate(auth.removeprefix('Bearer '))
                        authorized = is_admin or principal is not None
                    if not authorized:
                        return self.reply(401, {"error": "Unauthorized", "code":"UNAUTHORIZED", "retryable":False})
                    if self.path == '/api/native-share':
                        return self.reply(200, broker.save_native_share(data.get('device'), data))
                    if self.path.startswith('/api/clients/'):
                        if not is_admin:return self.reply(403, {'code':'FORBIDDEN','error':'Administrator credential required'})
                        if self.path == '/api/clients/register':return self.reply(200,broker.clients.register(data.get('devices')))
                        if self.path == '/api/clients/revoke':return self.reply(200,{'revoked':broker.revoke_client(data.get('clientId'))})
                        if self.path == '/api/clients/list':return self.reply(200,{'clients':broker.clients.list_clients()})
                        raise ValueError('Unknown endpoint')
                    data['_client'] = principal['clientId'] if principal else 'admin'
                    if principal:
                        allowed={'/api/devices','/api/command','/api/execute','/api/status','/api/action-status','/api/tasks/start','/api/tasks/get','/api/tasks/cancel','/api/native-artifacts/get'}
                        if self.path not in allowed:return self.reply(403,{'code':'FORBIDDEN','error':'Operation outside client scope'})
                        if self.path in {'/api/command','/api/execute'} and data.get('device') not in principal['devices']:
                            return self.reply(403,{'code':'FORBIDDEN','error':'Device outside client scope'})
                        data['_scopedClient']=principal['clientId']
                        data['_devices']=principal['devices']
                    result = broker.handle(self.path, data)
                    if principal and self.path == '/api/devices':
                        result={'devices':[item for item in result['devices'] if item['id'] in principal['devices']]}
            except BrokerError as error:
                return self.reply(error.status, {'error':str(error), 'code':error.code, 'retryable':error.status==429, **error.details})
            except KeyError:
                return self.reply(404, {'error':'Resource unavailable','code':'NOT_FOUND'})
            except (ValueError, TypeError) as error:
                return self.reply(400, {"error": str(error)})
            self.reply(200, result)

    class Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6 if ":" in host else socket.AF_INET
        daemon_threads=True
    httpd = Server((host, port), Handler)
    httpd.broker = broker
    return httpd


def server(port, token, credentials_file):
    httpd = make_server(port, token, credentials_file)
    print(f"Browser Bridge listening on 127.0.0.1:{httpd.server_port}", flush=True)
    httpd.serve_forever()


def api(url, token, path, data, *, timeout=None):
    parts=urlsplit(url)
    if parts.scheme not in ('http','https') or not parts.hostname: raise ValueError('HTTP(S) broker URL required')
    if timeout is None:
        timeout=max(15,min(65,float(data.get('waitMs',0))/1000+5))
    elif isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0 < timeout <= 65:
        raise ValueError('Transport timeout must be positive and at most 65 seconds')
    key=(parts.scheme,parts.hostname,parts.port)
    cache=getattr(_http_connections,'cache',None)
    if cache is None: cache={};_http_connections.cache=cache
    entry=cache.get(key)
    connection=entry[0] if entry and time.monotonic()-entry[1]<8 else None
    if entry and connection is None: entry[0].close()
    if connection is None:
        cls=http.client.HTTPSConnection if parts.scheme=='https' else http.client.HTTPConnection
        connection=cls(parts.hostname,parts.port,timeout=timeout)
    connection.timeout=timeout
    if connection.sock: connection.sock.settimeout(timeout)
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
    try:
        connection.request('POST',parts.path.rstrip('/')+path,body=payload,
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        response=connection.getresponse();body=response.read()
        cache[key]=(connection,time.monotonic())
        if response.status>=400:
            text=body.decode()
            try:detail=json.loads(text)
            except ValueError:detail=None
            # Surface the broker code first so agents can classify the failure (INVALID_ARGUMENT: ...).
            if isinstance(detail,dict) and isinstance(detail.get('error'),str):
                code=detail.get('code')
                text=detail['error'] if not isinstance(code,str) or detail['error'].startswith(code+':') else code+': '+detail['error']
            raise RuntimeError(text)
        return json.loads(body)
    except (OSError,http.client.HTTPException):
        connection.close();cache.pop(key,None)
        raise


_http_connections=threading.local()


def run_command(url, token, device, op, args, timeout=40, request=None, action_id=None):
    request = request or api
    args=dict(args)
    supplied=args.pop('actionId',None)
    if action_id is not None and supplied is not None and action_id!=supplied:
        raise ValueError('Conflicting action identifiers')
    action_id = action_id if action_id is not None else supplied
    if action_id is None and needs_durable_identity(op, args):
        action_id = secrets.token_urlsafe(24)
    if action_id is not None and (not isinstance(action_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,128}',action_id)):
        raise ValueError('Invalid actionId')
    try:
        result=request(url,token,'/api/execute',{'device':device,'op':op,'args':args,'actionId':action_id,'waitMs':min(40000,int(timeout*1000))})
        if 'error' in result: raise RuntimeError(result['error'])
        if result['state']=='done': return result.get('result')
        raise RuntimeError(f"Timed out; execution may have occurred. Do not retry blindly. Command ID: {result['id']}")
    except (OSError,http.client.HTTPException) as error:
        if action_id is None:
            raise RuntimeError('OBSERVATION_INTERRUPTED: read transport interrupted; request a fresh observation') from error
        raise RuntimeError(f'ACTION_UNCERTAIN: transport interrupted; reconcile Action ID: {action_id}; do not repeat') from error
    except (RuntimeError,ValueError) as error:
        if 'Unknown endpoint' not in str(error): raise
    identifier = request(url, token, "/api/command", {"device": device, "op": op, "args": args, "actionId":action_id})["id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = request(url, token, "/api/status", {"id": identifier})
        if result["state"] in ("done", "expired"):
            if "error" in result:
                raise RuntimeError(result["error"])
            return result.get("result")
        time.sleep(0.3)
    raise RuntimeError(f"Timed out; execution may have occurred. Do not retry blindly. Command ID: {identifier}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    parser.add_argument("--token-file", default=str(ROOT / "state/token"))
    sub = parser.add_subparsers(dest="action", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8766)
    sub.add_parser("devices")
    for name in ("enroll", "revoke"):
        action = sub.add_parser(name)
        action.add_argument("device")
    command = sub.add_parser("command")
    command.add_argument("device")
    command.add_argument("op", choices=sorted(OPERATIONS))
    command.add_argument("args", nargs="?", default="{}", help="JSON object")
    args = parser.parse_args()
    token = token_file(args.token_file)
    if args.action == "serve":
        server(args.port, token, Path(args.token_file).parent / "devices.json")
    elif args.action == "devices":
        print(json.dumps(api(args.url, token, "/api/devices", {}), indent=2))
    elif args.action in ("enroll", "revoke"):
        print(json.dumps(api(args.url, token, "/api/" + args.action, {"device": args.device}), indent=2))
    else:
        print(json.dumps(run_command(args.url, token, args.device, args.op, json.loads(args.args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
