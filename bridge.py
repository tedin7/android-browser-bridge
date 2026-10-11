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
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPERATIONS = {"tabs", "open", "activate", "close", "reload", "read", "click", "fill", "scroll"}


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
        self.devices = {}
        self.commands = {}
        self.pairings = {}
        self.credentials_file = Path(credentials_file) if credentials_file else None
        self.credentials = json.loads(self.credentials_file.read_text()) if self.credentials_file and self.credentials_file.exists() else {}
        self.devices.update({device: 0 for device in self.credentials})

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
        now = time.time()
        with self.lock:
            for code in list(self.pairings):
                if self.pairings[code]["expires"] < now:
                    del self.pairings[code]
            for key in list(self.commands):
                if now - self.commands[key]["created"] > 600:
                    del self.commands[key]
            if path == "/api/devices":
                return {"devices": [{"id": key, "lastSeen": seen, "online": now - seen < 15}
                                    for key, seen in self.devices.items()]}
            if path == "/api/status":
                command = self.commands.get(data.get("id"))
                if command is None:
                    raise ValueError("Unknown or expired command")
                result = {"state": command["state"]}
                for key in ("result", "error"):
                    if key in command:
                        result[key] = command[key]
                return result
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
                self.pairings = {code: item for code, item in self.pairings.items() if item["device"] != device}
                for command in self.commands.values():
                    if command["device"] == device and command["state"] in ("queued", "dispatched"):
                        command.update(state="expired", error="Device revoked")
                self.save_credentials()
                return {"ok": True}
            if path == "/api/poll":
                self.devices[device] = now
                for command in self.commands.values():
                    if command["device"] == device and command["state"] == "queued":
                        if now - command["created"] > 30:
                            command.update(state="expired", error="Browser did not pick up command within 30 seconds")
                            continue
                        command["state"] = "dispatched"
                        return {"command": {key: command[key] for key in ("id", "op", "args")}}
                return {"command": None}
            if path == "/api/command":
                if data.get("op") not in OPERATIONS or not isinstance(data.get("args", {}), dict):
                    raise ValueError("Invalid operation or arguments")
                if now - self.devices.get(device, 0) > 15:
                    raise ValueError("Device offline; open Firefox and enable the extension")
                if len(self.commands) >= 1000:
                    raise ValueError("Command limit reached")
                identifier = secrets.token_urlsafe(16)
                self.commands[identifier] = {"id": identifier, "device": device, "op": data["op"],
                    "args": data.get("args", {}), "created": now, "state": "queued"}
                return {"id": identifier}
            if path == "/api/result":
                command = self.commands.get(data.get("id"))
                if command is None or command["device"] != device or command["state"] not in ("dispatched", "done"):
                    raise ValueError("Invalid result")
                if command["state"] == "dispatched":
                    command["state"] = "done"
                    if "error" in data:
                        command["error"] = str(data["error"])[:1000]
                    else:
                        command["result"] = data.get("result")
                return {"ok": True}
            raise ValueError("Unknown endpoint")


def make_server(port, token, credentials_file=None, host="127.0.0.1"):
    broker = Broker(credentials_file)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value):
            payload = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"ok": True, "version": "0.1.0"})
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
                if not 0 < length <= 1_000_000:
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
    httpd = Server((host, port), Handler)
    httpd.broker = broker
    return httpd


def server(port, token, credentials_file):
    httpd = make_server(port, token, credentials_file)
    print(f"Browser Bridge listening on 127.0.0.1:{httpd.server_port}", flush=True)
    httpd.serve_forever()


def api(url, token, path, data):
    request = urllib.request.Request(url.rstrip("/") + path, json.dumps(data).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode()) from error


def run_command(url, token, device, op, args, timeout=40, request=None):
    request = request or api
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
