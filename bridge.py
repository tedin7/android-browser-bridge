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
import time
import http.client
from urllib.parse import urlsplit
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPERATIONS = {"tabs", "open", "activate", "close", "reload", "read", "click", "fill", "scroll",
    "capabilities", "navigate", "back", "forward", "frames", "screenshot", "inspect", "locate",
    "double_click", "click_point", "drag", "hover", "focus", "type", "clear", "select", "check", "press", "wait", "batch"}


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
    def __init__(self, credentials_file=None):
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.queues = defaultdict(deque)
        self.samples = defaultdict(lambda: deque(maxlen=512))
        self.device_info = {}
        self.leases = {}
        self.last_cleanup = 0.0
        self.devices = {}
        self.commands = {}
        self.pairings = {}
        self.credentials_file = Path(credentials_file) if credentials_file else None
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
        for key in ("result","error","timing"):
            if key in command: result[key]=command[key]
        return result

    def expire_queued(self, command):
        if command['state']=='queued' and time.time()-command['created'] > 30:
            command.update(state='expired',error='Browser did not pick up command within 30 seconds')
            self.changed.notify_all()

    def wait_result(self, identifier, seconds):
        deadline=time.monotonic()+seconds
        with self.changed:
            while True:
                command=self.commands.get(identifier)
                if command is None: raise ValueError('Unknown or expired command')
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
        if path == '/api/execute':
            seconds=self.wait_ms(data) if 'waitMs' in data else 40
            identifier=self.handle('/api/command',data)['id']
            return self.wait_result(identifier,seconds)
        if path == '/api/status':
            return self.wait_result(data.get('id'),self.wait_ms(data))
        now = time.time()
        with self.changed:
            if now-self.last_cleanup >= 10:
                self.last_cleanup=now
                for code in list(self.pairings):
                    if self.pairings[code]['expires'] < now: del self.pairings[code]
                for key in list(self.commands):
                    if now-self.commands[key]['created'] > 600: del self.commands[key]
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
                return {'operations':output,'pending':sum(c['state'] in ('queued','dispatched') for c in self.commands.values())}
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
                        command.update(state="expired", error="Device revoked")
                self.save_credentials()
                self.changed.notify_all()
                return {"ok": True}
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
                        command['state']='dispatched'
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
                if now >= self.leases.get(device,self.devices.get(device,0)+15):
                    raise ValueError("Device offline; open Firefox and enable the extension")
                if len(self.commands) >= 1000:
                    raise ValueError("Command limit reached")
                identifier = secrets.token_urlsafe(16)
                self.commands[identifier] = {"id": identifier, "device": device, "op": data["op"],
                    "args": data.get("args", {}), "created": now, "state": "queued",'startedAt':time.perf_counter()}
                self.queues[device].append(identifier)
                self.changed.notify_all()
                return {"id": identifier}
            if path == "/api/result":
                if data.get("_credential") is not None:
                    expected=self.credentials.get(device, "")
                    if not expected or not hmac.compare_digest(expected, data["_credential"]):
                        raise ValueError("Device revoked; pair again")
                command = self.commands.get(data.get("id"))
                if command is None or command["device"] != device or command["state"] not in ("dispatched", "done"):
                    raise ValueError("Invalid result")
                if command["state"] == "dispatched":
                    command["state"] = "done"
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
                return self.reply(200, {"ok": True, "version": "0.2.0"})
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
                    if self.path in ("/api/poll", "/api/result"):
                        authorized = broker.authorized_device(data.get("device", ""), auth.removeprefix("Bearer "))
                        if authorized: data['_credential']=auth.removeprefix('Bearer ')
                    else:
                        authorized = hmac.compare_digest(auth.encode(), ("Bearer " + token).encode())
                    if not authorized:
                        return self.reply(401, {"error": "Unauthorized"})
                    result = broker.handle(self.path, data)
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


def api(url, token, path, data):
    parts=urlsplit(url)
    if parts.scheme not in ('http','https') or not parts.hostname: raise ValueError('HTTP(S) broker URL required')
    timeout=max(15,min(65,float(data.get('waitMs',0))/1000+5))
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
        if response.status>=400: raise RuntimeError(body.decode())
        return json.loads(body)
    except (OSError,http.client.HTTPException):
        connection.close();cache.pop(key,None)
        raise


_http_connections=threading.local()


def run_command(url, token, device, op, args, timeout=40, request=None):
    request = request or api
    try:
        result=request(url,token,'/api/execute',{'device':device,'op':op,'args':args,'waitMs':int(timeout*1000)})
        if 'error' in result: raise RuntimeError(result['error'])
        if result['state']=='done': return result.get('result')
        raise RuntimeError(f"Timed out; execution may have occurred. Do not retry blindly. Command ID: {result['id']}")
    except (RuntimeError,ValueError) as error:
        if 'Unknown endpoint' not in str(error): raise
    identifier = request(url, token, "/api/command", {"device": device, "op": op, "args": args})["id"]
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
