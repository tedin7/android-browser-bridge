#!/usr/bin/env python3
"""Direct browser-to-Linux connection and stdio MCP. No relay or downloads."""
import argparse
import json
import os
import ssl
import sys
import threading
from pathlib import Path
from connection import connection_path, load_connection, save_connection, validate_origin
from bridge import make_server, token_file
from mcp_server import main as mcp_main


def validate_token_path(path):
    """Require an existing private admin token; attach never creates credentials."""
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("Token path must be an existing regular file")
    if os.name == "posix" and resolved.stat().st_mode & 0o077:
        raise ValueError("Token file must be private; set its permissions to 600")
    with resolved.open() as stream:
        value = stream.read(4097).strip()
    if not value or len(value) > 4096:
        raise ValueError("Token file must contain an existing nonempty admin token")
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", help="Attach MCP using an existing private connection JSON; never starts a server")
    parser.add_argument("--auto", action="store_true", help="Reuse the private runtime connection if present; otherwise run the local owner broker")
    parser.add_argument("--attach", help="Connect stdio MCP to an existing broker; never start or stop its HTTP server")
    parser.add_argument("--token-file", help="Existing private admin token file; required with --attach")
    parser.add_argument("--broker-only", action="store_true", help="Run a persistent HTTP broker without stdio MCP; clients connect using --attach")
    parser.add_argument("--local", action="store_true", help="Loopback-only development")
    parser.add_argument("--url", "--public-url", dest="origin", help="Address Android can reach, e.g. https://linux.example.org:8766")
    parser.add_argument("--listen", default="127.0.0.1", help="Bind address; use 0.0.0.0 to accept direct IPv4 connections")
    parser.add_argument("--fallback-url", action="append", default=[], help="Alternative address of THIS same broker; repeat up to four times")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--cert", help="PEM TLS certificate chain for direct HTTPS")
    parser.add_argument("--key", help="PEM TLS private key for direct HTTPS")
    parser.add_argument("--state-dir", default=str(Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "android-browser-bridge"))
    args = parser.parse_args()
    profile_path = Path(args.connection_file).expanduser() if args.connection_file else connection_path()
    use_profile = bool(args.connection_file) or (args.auto and (profile_path.exists() or profile_path.is_symlink()))
    if args.attach and (args.connection_file or args.auto):
        parser.error("--attach cannot be combined with --connection-file or --auto")
    if use_profile and (args.broker_only or args.token_file or args.cert or args.key or args.local):
        parser.error("Connection-profile attach cannot be combined with owner settings or --token-file")
    if len(args.fallback_url) > 4:
        parser.error("At most four fallback URLs allowed")
    if use_profile:
        profile = load_connection(profile_path)
        os.environ["BROWSER_BRIDGE_URL"] = profile["url"]
        os.environ["BROWSER_BRIDGE_PUBLIC_URL"] = validate_origin(args.origin or profile.get("browserUrl", profile["url"]))
        os.environ["BROWSER_BRIDGE_TOKEN"] = profile["token"]
        os.environ.pop("BROWSER_BRIDGE_TOKEN_FILE", None)
        os.environ["BROWSER_BRIDGE_CONNECTION_URLS"] = json.dumps([validate_origin(origin) for origin in args.fallback_url])
        if profile.get("device"):
            os.environ["BROWSER_BRIDGE_DEVICE"] = profile["device"]
        import mcp_server
        mcp_server.LOCAL_BROKER = None
        print("Browser Bridge attached using its private runtime connection; broker remains running.", file=sys.stderr)
        mcp_main()
        return
    if bool(args.cert) != bool(args.key):
        parser.error("Provide both --cert and --key")
    if args.attach and args.broker_only:
        parser.error("--attach and --broker-only cannot be combined")
    if args.attach and not args.token_file:
        parser.error("--attach requires --token-file for the existing broker's admin token")
    if args.token_file and not args.attach:
        parser.error("--token-file is for --attach; owner mode keeps its token in --state-dir")
    if args.attach and (args.cert or args.local):
        parser.error("--attach cannot be combined with --cert/--key or --local")
    if args.local:
        args.listen = "127.0.0.1"
    if args.listen != "127.0.0.1" and not args.origin:
        parser.error("Provide --url with the address reachable from Android")
    if args.origin:
        validate_origin(args.origin)
    if len(args.fallback_url) > 4:
        parser.error("At most four fallback URLs allowed")
    alternatives = [validate_origin(origin) for origin in args.fallback_url]
    if args.attach:
        attach_url = validate_origin(args.attach)
        existing_token = validate_token_path(args.token_file)
        os.environ["BROWSER_BRIDGE_URL"] = attach_url
        os.environ["BROWSER_BRIDGE_PUBLIC_URL"] = validate_origin(args.origin or attach_url)
        os.environ["BROWSER_BRIDGE_CONNECTION_URLS"] = json.dumps(alternatives)
        os.environ.pop("BROWSER_BRIDGE_TOKEN", None)
        os.environ["BROWSER_BRIDGE_TOKEN_FILE"] = str(existing_token)
        import mcp_server
        mcp_server.LOCAL_BROKER = None
        print("Browser Bridge attached to existing broker; client exit leaves the broker running.", file=sys.stderr)
        mcp_main()
        return
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
    os.environ.pop("BROWSER_BRIDGE_TOKEN", None)
    os.environ["BROWSER_BRIDGE_TOKEN_FILE"] = str(state / "token")
    profile_url = validate_origin(args.origin) if args.cert and args.origin else local_url
    save_connection({"url": profile_url, "token": token, "browserUrl": os.environ["BROWSER_BRIDGE_PUBLIC_URL"]}, state / "connection.json")
    import mcp_server
    mcp_server.LOCAL_BROKER = httpd.broker
    if args.broker_only:
        print("Browser Bridge persistent broker ready. Connect MCP clients with --attach and its private token file.", file=sys.stderr)
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()
        return
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
    except KeyboardInterrupt:
        pass
    except (RuntimeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
