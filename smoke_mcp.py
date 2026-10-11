"""Exercise the packaged MCP over stdio and HTTP with a simulated browser."""
import argparse
import base64
import json
import os
import select
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from bridge import api


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true", help="Test direct network listener instead of loopback")
    parser.add_argument("--tls", action="store_true", help="Direct HTTPS with a test certificate trusted only by this test")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as state, tempfile.TemporaryFile(mode="w+") as logs:
        command = [sys.executable, "android-browser-mcp.pyz", "--state-dir", state, "--port", "0"]
        if args.direct or args.tls:
            import socket
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            command = [sys.executable, "android-browser-mcp.pyz", "--state-dir", state, "--listen", "0.0.0.0", "--port", str(port), "--url", f"http://127.0.0.1:{port}"]
            if args.tls:
                certificate = str(Path(state) / "test-cert.pem")
                key = str(Path(state) / "test-key.pem")
                subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1", "-keyout", key, "-out", certificate], check=True, stdout=logs, stderr=logs)
                command[-1] = f"https://127.0.0.1:{port}"
                command += ["--cert", certificate, "--key", key]
                os.environ["SSL_CERT_FILE"] = certificate
        else:
            command.append("--local")
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logs, text=True)

        def rpc(identifier, method, params):
            child.stdin.write(json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}) + "\n")
            child.stdin.flush()
            if not select.select([child.stdout], [], [], 120)[0]:
                raise RuntimeError("MCP response timed out")
            line = child.stdout.readline()
            if not line:
                logs.seek(0)
                raise RuntimeError("MCP exited: " + logs.read()[-2000:])
            reply = json.loads(line)
            assert reply["id"] == identifier, reply
            return reply["result"]

        try:
            result = rpc(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}})
            assert result["serverInfo"]["name"] == "android-browser-bridge"
            assert len(rpc(2, "tools/list", {})["tools"]) == 5
            pair = rpc(3, "tools/call", {"name": "browser_pair", "arguments": {"device": "test-tablet"}})
            assert not pair.get("isError"), pair
            bundle = json.loads(pair["content"][0]["text"])
            encoded = bundle["pairing"].split(".", 1)[1]
            pairing = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            deadline = time.monotonic() + 30
            while True:
                try:
                    paired = api(pairing["url"], "", "/api/pair", {"code": pairing["code"]})
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(1)
            token, device = paired["token"], paired["device"]
            api(pairing["url"], token, "/api/poll", {"device": device})
            worker_errors = []

            def browser_worker():
                try:
                    for _ in range(40):
                        command = api(pairing["url"], token, "/api/poll", {"device": device})["command"]
                        if command:
                            assert command["op"] == "tabs"
                            api(pairing["url"], token, "/api/result", {"device": device, "id": command["id"], "result": [{"id": 42, "title": "Simulated browser"}]})
                            return
                        time.sleep(0.25)
                    raise RuntimeError("Browser worker timed out")
                except Exception as error:
                    worker_errors.append(error)

            thread = threading.Thread(target=browser_worker)
            thread.start()
            reply = rpc(4, "tools/call", {"name": "browser_command", "arguments": {"device": device, "op": "tabs"}})
            thread.join()
            assert not worker_errors, worker_errors
            assert not reply.get("isError"), reply
            assert json.loads(reply["content"][0]["text"])[0]["id"] == 42
            revoke = rpc(5, "tools/call", {"name": "browser_revoke", "arguments": {"device": device}})
            assert not revoke.get("isError"), revoke
            print("PASS: packaged stdio MCP → " + ("direct HTTPS (certificate verified)" if args.tls else "direct listener" if args.direct else "local HTTP") + " → simulated browser → command result → revoke")
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=15)


if __name__ == "__main__":
    main()
