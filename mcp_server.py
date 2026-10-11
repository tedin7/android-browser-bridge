#!/usr/bin/env python3
"""MCP stdio adapter. No third-party dependencies; stdout is JSON-RPC only."""
import json
import os
import sys
import base64
from bridge import OPERATIONS, ROOT, api, run_command
LOCAL_BROKER = None


def broker_api(url, token, path, data):
    if LOCAL_BROKER is not None:
        return LOCAL_BROKER.handle(path, data)
    return api(url, token, path, data)

TOOLS = [
    {"name": "browser_pair", "description": "Generate a one-use pairing string for YOUR Android browser. Paste it into the Browser Bridge extension within five minutes.",
     "inputSchema": {"type": "object", "required": ["device"], "properties": {"device": {"type": "string", "pattern": "^[a-zA-Z0-9_-]{1,64}$"}}, "additionalProperties": False}},
    {"name": "browser_revoke", "description": "Revoke a browser's access and cancel pending commands.",
     "inputSchema": {"type": "object", "required": ["device"], "properties": {"device": {"type": "string"}}, "additionalProperties": False}},
    {"name": "browser_devices", "description": "List opted-in browsers and their recent availability.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "browser_command", "description": "Control your opted-in browser. Read/tabs inspect; click/fill use one CSS selector. HTTP(S) open only. No arbitrary JavaScript.",
     "inputSchema": {"type": "object", "required": ["device", "op"], "additionalProperties": False,
         "properties": {"device": {"type": "string"}, "op": {"type": "string", "enum": sorted(OPERATIONS)},
             "args": {"type": "object", "properties": {
                 "tabId": {"type": "integer"}, "url": {"type": "string"},
                 "selector": {"type": "string"}, "value": {"type": "string"},
                 "x": {"type": "number"}, "y": {"type": "number"}}, "additionalProperties": False}}}}
]


def handle(message):
    method = message.get("method")
    if method == "initialize":
        return {"protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}}, "serverInfo": {"name": "android-browser-bridge", "version": "0.1.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        try:
            url = os.environ.get("BROWSER_BRIDGE_URL", "http://127.0.0.1:8766")
            token = os.environ.get("BROWSER_BRIDGE_TOKEN")
            if not token:
                token = open(os.environ.get("BROWSER_BRIDGE_TOKEN_FILE", str(ROOT / "state/token"))).read().strip()
            params = message.get("params", {})
            args = params.get("arguments", {})
            if params["name"] == "browser_devices":
                result = broker_api(url, token, "/api/devices", {})
            elif params["name"] == "browser_pair":
                result = broker_api(url, token, "/api/enroll", {"device": args["device"]})
                origin = os.environ.get("BROWSER_BRIDGE_PUBLIC_URL", url)
                payload = json.dumps({"url": origin, "urls": json.loads(os.environ.get("BROWSER_BRIDGE_CONNECTION_URLS", "[]")), "code": result["code"]}).encode()
                result = {"device": args["device"], "pairing": "BB1." + base64.urlsafe_b64encode(payload).decode().rstrip("="),
                          "expiresIn": result["expiresIn"], "installPage": origin + "/"}
            elif params["name"] == "browser_revoke":
                result = broker_api(url, token, "/api/revoke", {"device": args["device"]})
            elif params["name"] == "browser_command":
                result = run_command(url, token, args["device"], args["op"], args.get("args", {}), request=broker_api)
            else:
                raise ValueError("Unknown tool")
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        except Exception as error:
            return {"isError": True, "content": [{"type": "text", "text": str(error)}]}
    raise ValueError("Method not found")


def main():
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if "id" not in message:
                continue
            try:
                reply = {"jsonrpc": "2.0", "id": message["id"], "result": handle(message)}
            except ValueError as error:
                reply = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": str(error)}}
        except (ValueError, TypeError):
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
