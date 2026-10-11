#!/usr/bin/env python3
"""Direct browser-to-Linux connection and stdio MCP. No relay or downloads."""
import argparse
import ipaddress
import json
import os
import ssl
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit
from bridge import make_server, token_file
from mcp_server import main as mcp_main


def validate_origin(origin):
    parts = urlsplit(origin)
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/") or not parts.hostname:
        raise ValueError("Use an HTTP(S) origin without path, credentials or query")
    if parts.scheme == "https":
        return origin.rstrip("/")
    if parts.scheme == "http":
        if parts.hostname == "localhost":
            return origin.rstrip("/")
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            address = None
        networks = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7"]
        if address and any(address in ipaddress.ip_network(network) for network in networks if address.version == ipaddress.ip_network(network).version):
            return origin.rstrip("/")
    raise ValueError("Internet connections require HTTPS; HTTP is limited to trusted private networks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="Loopback-only development")
    parser.add_argument("--url", "--public-url", dest="origin", help="Address Android can reach, e.g. https://linux.example.org:8766")
    parser.add_argument("--listen", default="127.0.0.1", help="Bind address; use 0.0.0.0 to accept direct IPv4 connections")
    parser.add_argument("--fallback-url", action="append", default=[], help="Alternative address of THIS same broker; repeat up to four times")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--cert", help="PEM TLS certificate chain for direct HTTPS")
    parser.add_argument("--key", help="PEM TLS private key for direct HTTPS")
    parser.add_argument("--state-dir", default=str(Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "android-browser-bridge"))
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key):
        parser.error("Provide both --cert and --key")
    if args.local:
        args.listen = "127.0.0.1"
    if args.listen != "127.0.0.1" and not args.origin:
        parser.error("Provide --url with the address reachable from Android")
    if args.origin:
        validate_origin(args.origin)
    if len(args.fallback_url) > 4:
        parser.error("At most four fallback URLs allowed")
    alternatives = [validate_origin(origin) for origin in args.fallback_url]
    state = Path(args.state_dir)
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    token = token_file(state / "token")
    httpd = make_server(args.port, token, state / "devices.json", host=args.listen)
    if args.cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.cert, args.key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    scheme = "https" if args.cert else "http"
    local_host = "127.0.0.1" if args.listen == "0.0.0.0" else ("::1" if args.listen == "::" else args.listen)
    if ":" in local_host:
        local_host = "[" + local_host + "]"
    local_url = f"{scheme}://{local_host}:{httpd.server_port}"
    os.environ["BROWSER_BRIDGE_URL"] = local_url
    os.environ["BROWSER_BRIDGE_PUBLIC_URL"] = validate_origin(args.origin or local_url)
    os.environ["BROWSER_BRIDGE_CONNECTION_URLS"] = json.dumps(alternatives)
    os.environ["BROWSER_BRIDGE_TOKEN_FILE"] = str(state / "token")
    import mcp_server
    mcp_server.LOCAL_BROKER = httpd.broker
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        print("Browser Bridge ready (direct mode). Use MCP browser_pair to connect Android.", file=sys.stderr)
        mcp_main()
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
