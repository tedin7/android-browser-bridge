#!/usr/bin/env python3
"""Install the reproducible single-file MCP without root or dependency downloads."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from launcher import validate_origin

parser = argparse.ArgumentParser()
parser.add_argument("--url", help="Address reachable from Android")
parser.add_argument("--listen", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8766)
args = parser.parse_args()
if args.url:
    validate_origin(args.url)
root = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(root / "build.py")], check=True, stdout=sys.stderr)
destination = Path.home() / ".local/share/android-browser-bridge"
destination.mkdir(parents=True, exist_ok=True)
target = destination / "android-browser-mcp.pyz"
shutil.copy2(root / target.name, target)
command_args = [str(target), "--listen", args.listen, "--port", str(args.port)]
if args.url:
    command_args += ["--url", args.url]
config = {"mcpServers": {"android-browser": {"command": sys.executable, "args": command_args}}}
config_path = destination / "mcp-config.json"
config_path.write_text(json.dumps(config, indent=2) + "\n")
print(json.dumps(config, indent=2))
print(f"Config saved to {config_path}; merge this server into your MCP client's existing configuration.", file=sys.stderr)
