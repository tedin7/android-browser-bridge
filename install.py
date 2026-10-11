#!/usr/bin/env python3
"""Install the reproducible single-file MCP without root or dependency downloads."""
import argparse
from datetime import datetime, timezone
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from launcher import validate_origin, validate_token_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Address reachable from Android; optionally different from the attached broker address")
    parser.add_argument("--attach", help="Generate an MCP client for an already-running broker")
    parser.add_argument("--token-file", help="Existing private admin token file; required with --attach")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if args.url:
        validate_origin(args.url)
    if args.attach and not args.token_file:
        parser.error("--attach requires --token-file")
    if args.token_file and not args.attach:
        parser.error("--token-file requires --attach")
    attach_url = validate_origin(args.attach) if args.attach else None
    attach_token = validate_token_path(args.token_file) if args.attach else None
    root = Path(__file__).resolve().parent
    destination = Path.home() / ".local/share/android-browser-bridge"
    config_path = destination / "mcp-config.json"
    # Validate before building/copying and preserve all other configured servers
    # and top-level settings. Never print previously stored credentials.
    existing = {}
    if config_path.exists():
        existing = json.loads(config_path.read_text())
        if not isinstance(existing, dict) or not isinstance(existing.get("mcpServers", {}), dict):
            raise ValueError("Existing MCP config must contain an object with an optional mcpServers object")
    subprocess.run([sys.executable, str(root / "build.py")], check=True, stdout=sys.stderr)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "android-browser-mcp.pyz"
    staging = destination / (target.name + ".tmp-" + secrets.token_hex(4))
    try:
        shutil.copy2(root / target.name, staging)
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    command_args = [str(target)]
    if attach_url:
        command_args += ["--attach", attach_url, "--token-file", str(attach_token)]
    else:
        command_args += ["--listen", args.listen, "--port", str(args.port)]
    if args.url:
        command_args += ["--url", args.url]
    server_config = {"command": sys.executable, "args": command_args}
    config = {**existing, "mcpServers": {**existing.get("mcpServers", {}), "android-browser": server_config}}
    if config_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = destination / (config_path.name + ".bak-" + stamp + "-" + secrets.token_hex(4))
        shutil.copy2(config_path, backup)
        backup.chmod(0o600)
    config_staging = destination / (config_path.name + ".tmp-" + secrets.token_hex(4))
    try:
        with config_staging.open("x") as stream:
            config_staging.chmod(0o600)
            stream.write(json.dumps(config, indent=2) + "\n")
        os.replace(config_staging, config_path)
    finally:
        config_staging.unlink(missing_ok=True)
    print(json.dumps({"mcpServers": {"android-browser": server_config}}, indent=2))
    print(f"Config saved to {config_path}; merge this server into your MCP client's existing configuration.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
