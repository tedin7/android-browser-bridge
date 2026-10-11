"""Real Firefox integration test in a fresh profile; no user browser/session data.

Requires Firefox desktop, npm and web-ext. This does NOT test Android Firefox.
Only a temporary test copy opts in automatically, and only fixture content is used.
"""
import base64
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURE = b'''<!doctype html><html><head><title>Bridge fixture</title></head><body>
<h1>Browser Bridge real Firefox fixture</h1><p id="result">not clicked</p>
<button id="go" onclick="document.getElementById('result').textContent='clicked successfully'">Click me</button>
<input id="name" oninput="document.getElementById('echo').textContent=this.value"><p id="echo"></p>
</body></html>'''


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(FIXTURE)))
        self.end_headers()
        self.wfile.write(FIXTURE)

    def log_message(self, *_):
        pass


def main():
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    fixture_url = f"http://127.0.0.1:{fixture.server_port}/fixture"
    with tempfile.TemporaryDirectory(prefix="bridge-real-firefox-") as directory:
        directory = Path(directory)
        with tempfile.TemporaryFile(mode="w+") as logs:
            mcp = subprocess.Popen([sys.executable, str(ROOT / "android-browser-mcp.pyz"), "--local", "--port", "0", "--state-dir", str(directory / "state")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logs, text=True)
            runner = None
            request_id = 0

            def rpc(method, params):
                nonlocal request_id
                request_id += 1
                mcp.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
                mcp.stdin.flush()
                if not select.select([mcp.stdout], [], [], 45)[0]:
                    raise RuntimeError("MCP response timed out")
                line = mcp.stdout.readline()
                if not line:
                    raise RuntimeError("MCP exited")
                response = json.loads(line)
                if "error" in response:
                    raise RuntimeError(str(response["error"]))
                return response["result"]

            def tool(name, args=None):
                result = rpc("tools/call", {"name": name, "arguments": args or {}})
                if result.get("isError"):
                    raise RuntimeError(result["content"][0]["text"])
                return json.loads(result["content"][0]["text"])

            def operation(op, args=None):
                return tool("browser_command", {"device": "fixture", "op": op, "args": args or {}})

            try:
                rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "real-firefox-test", "version": "1"}})
                pairing = tool("browser_pair", {"device": "fixture"})["pairing"].split(".", 1)[1]
                bundle = json.loads(base64.urlsafe_b64decode(pairing + "=" * (-len(pairing) % 4)))
                extension = directory / "extension"
                shutil.copytree(ROOT / "extension", extension)
                bootstrap = '''(async () => {
  const bundle = BUNDLE;
  const response = await fetch(bundle.url + '/api/pair', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code: bundle.code})});
  if (!response.ok) throw Error('Test pairing failed');
  const paired = await response.json();
  await browser.storage.local.set({url: bundle.url, urls: [bundle.url], device: paired.device, token: paired.token, enabled: true});
  await browser.tabs.create({url: FIXTURE_URL});
})();
'''.replace("BUNDLE", json.dumps(bundle)).replace("FIXTURE_URL", json.dumps(fixture_url))
                (extension / "test-bootstrap.js").write_text(bootstrap)
                manifest = json.loads((extension / "manifest.json").read_text())
                manifest["background"]["scripts"].append("test-bootstrap.js")
                (extension / "manifest.json").write_text(json.dumps(manifest))
                env = os.environ.copy()
                env.update({"MOZ_HEADLESS": "1", "MOZ_DISABLE_CONTENT_SANDBOX": "1", "MOZ_DISABLE_RDD_SANDBOX": "1", "MOZ_DISABLE_GPU_SANDBOX": "1"})
                runner = subprocess.Popen(["npm", "exec", "--yes", "--package", "web-ext@10", "--", "web-ext", "run", "--no-config-discovery", "--no-input", "--no-reload", "--source-dir", str(extension), "--firefox", "/usr/bin/firefox", "--args=-headless"],
                    stdout=logs, stderr=logs, env=env, start_new_session=True)
                print("Started Firefox with a fresh temporary test profile.", flush=True)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    devices = tool("browser_devices")["devices"]
                    if any(device["id"] == "fixture" and device["online"] for device in devices):
                        break
                    if runner.poll() is not None:
                        raise RuntimeError("Firefox runner exited")
                    time.sleep(1)
                else:
                    raise RuntimeError("Real Firefox did not connect within 60 seconds")
                print("Real Firefox extension paired and polling through MCP.", flush=True)
                tabs = operation("tabs")
                tab = next(tab for tab in tabs if tab.get("url") == fixture_url)
                tab_id = tab["id"]
                deadline = time.monotonic() + 15
                while True:
                    page = operation("read", {"tabId": tab_id})
                    if "real Firefox fixture" in page.get("text", ""):
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError("Fixture not loaded")
                    time.sleep(0.5)
                operation("click", {"tabId": tab_id, "selector": "#go"})
                assert "clicked successfully" in operation("read", {"tabId": tab_id})["text"]
                text = "MCP filled 'quotes' and unicode à correctly"
                operation("fill", {"tabId": tab_id, "selector": "#name", "value": text})
                page = operation("read", {"tabId": tab_id})
                assert text in page["text"]
                assert any(element["selector"] == "#go" for element in page["elements"])
                operation("scroll", {"tabId": tab_id, "y": 100})
                operation("activate", {"tabId": tab_id})
                new_tab = operation("open", {"url": fixture_url + "?opened=1"})["id"]
                operation("reload", {"tabId": new_tab})
                operation("close", {"tabId": new_tab})
                tool("browser_revoke", {"device": "fixture"})
                print("PASS: real Firefox + real extension + packaged stdio MCP: pair, tabs, read, click, fill, scroll, activate, open, reload, close, revoke. Android is NOT tested.", flush=True)
            except Exception:
                logs.seek(0)
                # Runtime credentials are not printed; web-ext logs contain no
                # page data in this test. Output only the final runner messages.
                print(logs.read()[-5000:], file=sys.stderr)
                raise
            finally:
                if runner and runner.poll() is None:
                    os.killpg(runner.pid, signal.SIGTERM)
                    try:
                        runner.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(runner.pid, signal.SIGKILL)
                        runner.wait()
                mcp.stdin.close()
                try:
                    mcp.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    mcp.terminate()
                    mcp.wait(timeout=10)
    fixture.shutdown()
    fixture.server_close()


if __name__ == "__main__":
    main()
