#!/usr/bin/env python3
"""Install Browser Bridge and optionally register Codex using discovered settings."""
import argparse
import fcntl
import hmac
import http.client
from datetime import datetime, timezone
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from launcher import validate_origin, validate_token_path
from connection import connection_path, load_connection, save_connection

NATIVE_BINDINGS = ("BROWSER_BRIDGE_ANDROID_PACKAGE", "BROWSER_BRIDGE_ANDROID_DEVICE")


def _codex_executable():
    configured = os.environ.get("CODEX_CLI_PATH")
    if configured and Path(configured).is_file() and os.access(configured, os.X_OK):
        return str(Path(configured).resolve())
    return shutil.which("codex")


def _claude_executable():
    configured = os.environ.get("CLAUDE_CLI_PATH")
    if configured and Path(configured).is_file() and os.access(configured, os.X_OK):
        return str(Path(configured).resolve())
    return shutil.which("claude")


def _claude_config_path():
    return Path.home() / ".claude.json"


def _read_claude_config():
    path = _claude_config_path()
    raw = path.read_bytes() if path.exists() else None
    try:
        config = json.loads(raw) if raw is not None else {}
    except ValueError:
        raise ValueError("Existing Claude configuration is invalid; preserved unchanged") from None
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("Existing Claude configuration must contain an optional mcpServers object")
    return raw, config


def _claude_servers():
    return list(_read_claude_config()[1].get("mcpServers", {}).values())


def register_claude(server_config):
    """Merge user-scope stdio registration, retrying observed concurrent edits."""
    path = _claude_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(8):
        raw, config = _read_claude_config()
        servers = config.get("mcpServers", {})
        name = _server_name(servers)
        previous = servers.get(name, {})
        value = {**previous, **server_config, "type": "stdio"}
        value["env"] = {**previous.get("env", {}), **server_config.get("env", {})}
        # Credentials belong only in the canonical private profile.
        for key in ("BROWSER_BRIDGE_TOKEN", "BROWSER_BRIDGE_TOKEN_FILE", "BROWSER_BRIDGE_URL", "BROWSER_BRIDGE_CONNECTION_FILE"):
            value["env"].pop(key, None)
        if not value["env"]:
            value.pop("env")
        updated = {**config, "mcpServers": {**servers, name: value}}
        if updated == config:
            path.chmod(0o600)
            return name
        staging = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
        try:
            with staging.open("x") as stream:
                staging.chmod(0o600)
                stream.write(json.dumps(updated, indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            if (path.read_bytes() if path.exists() else None) != raw:
                continue
            _backup(path)
            if (path.read_bytes() if path.exists() else None) != raw:
                continue
            os.replace(staging, path)
            return name
        finally:
            staging.unlink(missing_ok=True)
    raise RuntimeError("Claude configuration kept changing concurrently; retry installation")


def _codex_servers(executable=None):
    executable = executable or _codex_executable()
    if not executable:
        return []
    result = subprocess.run([executable, "mcp", "list", "--json"], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Could not inspect Codex MCP configuration; no existing servers were changed")
    try:
        records = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError("Codex returned invalid MCP configuration data") from None
    if not isinstance(records, list):
        raise RuntimeError("Codex returned unexpected MCP configuration data")
    return records


def _transport(record):
    value = record.get("transport", record)
    return value if isinstance(value, dict) else {}


def is_genuine_bridge(record):
    """Recognize this project's executable, not just an occupied server name."""
    transport = _transport(record)
    if transport.get("type", "stdio") != "stdio":
        return False
    values = [transport.get("command"), *(transport.get("args") or [])]
    for value in values:
        if not isinstance(value, str):
            continue
        file = Path(value).expanduser()
        if not file.is_absolute():
            file = Path(transport.get("cwd") or Path.cwd()) / file
        if file.name == "android-browser-mcp.pyz" and file.is_file():
            try:
                with ZipFile(file) as archive:
                    if {"bridge.py", "mcp_server.py", "launcher.py", "android-browser-bridge.xpi"} <= set(archive.namelist()):
                        return True
            except (OSError, BadZipFile):
                pass
        if file.name == "mcp_server.py" and file.parent.name == "android-browser-bridge":
            try:
                manifest = json.loads((file.parent / "extension/manifest.json").read_text())
                if manifest.get("browser_specific_settings", {}).get("gecko", {}).get("id") == "android-browser-bridge@local.invalid" and (file.parent / "bridge.py").is_file():
                    return True
            except (OSError, ValueError):
                pass
    return False


def _flag(values, *names):
    for name in names:
        if name in values:
            index = values.index(name)
            if index + 1 < len(values):
                return values[index + 1]
    return None


def _profile_from_record(record):
    if not is_genuine_bridge(record):
        return None
    transport = _transport(record)
    args, env = transport.get("args") or [], transport.get("env") or {}
    profile_file = _flag(args, "--connection-file") or env.get("BROWSER_BRIDGE_CONNECTION_FILE")
    if profile_file:
        return load_connection(profile_file)
    url = _flag(args, "--attach") or env.get("BROWSER_BRIDGE_URL")
    token_path = _flag(args, "--token-file") or env.get("BROWSER_BRIDGE_TOKEN_FILE")
    token = env.get("BROWSER_BRIDGE_TOKEN")
    if not url or not (token_path or token):
        return None
    if token_path:
        token = validate_token_path(token_path).read_text().strip()
    profile = {"url": validate_origin(url), "token": token}
    public_url = _flag(args, "--url", "--public-url") or env.get("BROWSER_BRIDGE_PUBLIC_URL")
    if public_url:
        profile["browserUrl"] = validate_origin(public_url)
    device = env.get("BROWSER_BRIDGE_ANDROID_DEVICE")
    if device:
        profile["device"] = device
    return profile


def _generated_config():
    path = Path.home() / ".local/share/android-browser-bridge/mcp-config.json"
    if not path.exists():
        return {}
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("Existing MCP config must contain an object with an optional mcpServers object")
    return config


def discover_connection_profile():
    """Reuse private profile or migrate genuine existing bridge configuration.

    Returns a private JSON path or None. Never fabricates remote credentials,
    prints tokens, alters unrelated MCP servers, or probes arbitrary services.
    """
    path = connection_path()
    if path.exists() or os.environ.get("BROWSER_BRIDGE_CONNECTION_FILE"):
        load_connection(path)
        return path.resolve()
    generated = _generated_config()
    records = list(generated.get("mcpServers", {}).values()) + _codex_servers() + _claude_servers()
    for record in records:
        profile = _profile_from_record(record)
        if profile is not None:
            return save_connection(profile, path).resolve()
    return None


def _native_bindings(records, profile):
    bindings = {key: os.environ[key] for key in NATIVE_BINDINGS if os.environ.get(key)}
    for record in records:
        if not is_genuine_bridge(record):
            continue
        try:
            candidate = _profile_from_record(record)
        except (ValueError, OSError):
            # A selected valid canonical profile does not depend on stale
            # registrations for a different or removed connection.
            continue
        if profile is not None and candidate is not None and candidate["url"] != profile["url"]:
            continue
        env = _transport(record).get("env") or {}
        for key in NATIVE_BINDINGS:
            if env.get(key):
                bindings.setdefault(key, env[key])
    return bindings


def _server_name(servers):
    base = "android-browser"
    if base not in servers or is_genuine_bridge(servers[base]):
        return base
    for name, record in servers.items():
        if name.startswith(base + "-") and is_genuine_bridge(record):
            return name
    number = 2
    while f"{base}-{number}" in servers:
        number += 1
    return f"{base}-{number}"


def _backup(path):
    if not path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup = path.with_name(path.name + ".bak-" + stamp + "-" + secrets.token_hex(4))
    shutil.copy2(path, backup)
    backup.chmod(0o600)


def _write_config(path, config):
    _backup(path)
    staging = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    try:
        with staging.open("x") as stream:
            staging.chmod(0o600)
            stream.write(json.dumps(config, indent=2) + "\n")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _probe_profile(profile, timeout=1.0):
    """Authenticate a fixed broker endpoint without exposing its response."""
    parts = urlsplit(profile["url"])
    connection_class = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    connection = connection_class(parts.hostname, parts.port, timeout=timeout)
    try:
        connection.request("POST", "/api/devices", body="{}", headers={"Authorization": "Bearer " + profile["token"], "Content-Type": "application/json"})
        response = connection.getresponse()
        body = response.read(1024 * 1024)
        if response.status != 200:
            return False
        value = json.loads(body)
        return isinstance(value, dict) and isinstance(value.get("devices"), list)
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        connection.close()


def _pid_alive(path):
    try:
        pid = int(path.read_text().strip())
        if pid <= 1:
            return False
        try:
            if Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].strip().split()[0] == "Z":
                return False
        except (OSError, IndexError):
            pass
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _private_text(path, text):
    staging = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    try:
        descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(text)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def ensure_persistent_broker(target, args, profile_file=None):
    """Reuse an authenticated broker or bootstrap one known local owner.

    The private bootstrap lock coordinates concurrent cold installations. A
    stopped owner can be restarted only when its canonical loopback profile
    matches the existing private owner token. Unknown connections fail closed.
    """
    canonical = connection_path().resolve()
    if profile_file is not None:
        profile_file = Path(profile_file).resolve()
        profile = load_connection(profile_file)
        if _probe_profile(profile):
            return profile_file
    state = canonical.parent
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = state / "bootstrap.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        # A simultaneous installer may already have created the real owner.
        selected = profile_file or (canonical if canonical.exists() else None)
        profile = load_connection(selected) if selected else None
        if profile is not None and _probe_profile(profile):
            return Path(selected).resolve()
        pid_path = state / "broker.pid"
        runtime_profile = state / "connection.json"
        if profile is None and canonical != runtime_profile and runtime_profile.exists():
            # Changing only the client-profile filename must not spawn a
            # second owner when the authenticated local owner is already live.
            try:
                candidate = load_connection(runtime_profile)
                owner_token = validate_token_path(state / "token").read_text().strip()
                if hmac.compare_digest(candidate["token"], owner_token) and _probe_profile(candidate):
                    save_connection(candidate, canonical)
                    return canonical
            except (OSError, ValueError):
                pass
        if profile is not None:
            parts = urlsplit(profile["url"])
            owned = Path(selected).resolve() == canonical and parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")
            try:
                owner_token = validate_token_path(state / "token").read_text().strip()
                owned = owned and hmac.compare_digest(profile["token"], owner_token)
            except (OSError, ValueError):
                owned = False
            if not owned:
                raise RuntimeError("Existing browser connection is unavailable or unauthorized; no replacement broker was created")
            port = parts.port or 80
        else:
            if args.listen != "127.0.0.1":
                raise ValueError("Automatic fresh Codex setup is loopback-only; configure an existing reachable broker before using a different listen address")
            port = args.port if args.port is not None else 0
        process = None
        if not _pid_alive(pid_path):
            log_path = state / "broker.log"
            log_descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.fchmod(log_descriptor, 0o600)
            environment = {**os.environ, "BROWSER_BRIDGE_CONNECTION_FILE": str(canonical)}
            command = [sys.executable, str(target), "--broker-only", "--local", "--port", str(port), "--state-dir", str(state)]
            browser_url = args.url or (profile.get("browserUrl") if profile else None)
            if browser_url:
                command += ["--url", browser_url]
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log_descriptor, env=environment, start_new_session=True, close_fds=True)
            finally:
                os.close(log_descriptor)
            _private_text(pid_path, str(process.pid) + "\n")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                # Owner state is isolated and always writes connection.json.
                # A configured client profile may have a different filename.
                source = canonical if canonical.exists() else runtime_profile
                current = load_connection(source)
                if source != canonical:
                    owner_token = validate_token_path(state / "token").read_text().strip()
                    if not hmac.compare_digest(current["token"], owner_token):
                        raise ValueError("Owner runtime profile does not match its private token")
                if _probe_profile(current, min(1.0, max(0.05, deadline - time.monotonic()))):
                    if profile is not None or source != canonical:
                        # Preserve authorized browser metadata, or publish the
                        # authenticated owner endpoint to the selected profile.
                        save_connection(profile if profile is not None else current, canonical)
                    return canonical
            except (OSError, ValueError):
                pass
            if process is not None and process.poll() is not None:
                raise RuntimeError("The local persistent broker could not start; inspect its private broker.log")
            time.sleep(0.05)
        raise RuntimeError("The local persistent broker did not become authenticated within ten seconds; inspect its private broker.log")
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _install_package(root, destination):
    destination.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination / "package.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    target = destination / "android-browser-mcp.pyz"
    staging = destination / (target.name + ".tmp-" + secrets.token_hex(4))
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        # Concurrent installers must not read a partially rebuilt zipapp.
        subprocess.run([sys.executable, str(root / "build.py")], check=True, stdout=sys.stderr)
        shutil.copy2(root / target.name, staging)
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", action="store_true", help="Discover the connection and register this MCP automatically in Codex")
    parser.add_argument("--claude", action="store_true", help="Discover the connection and register this MCP automatically in Claude Code")
    parser.add_argument("--auto", action="store_true", help="Reuse a private profile or discover existing Browser Bridge settings")
    parser.add_argument("--url", help="Address reachable from Android; optionally different from the attached broker address")
    parser.add_argument("--attach", help="Generate an MCP client for an already-running broker")
    parser.add_argument("--token-file", help="Existing private admin token file; required with --attach")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="Owner port; automatic Codex bootstrap chooses a free port by default")
    args = parser.parse_args()
    if args.url:
        validate_origin(args.url)
    if args.attach and not args.token_file:
        parser.error("--attach requires --token-file")
    if args.token_file and not args.attach:
        parser.error("--token-file requires --attach")
    executable = _codex_executable() if args.codex else None
    if args.codex and not executable:
        raise RuntimeError("Codex CLI was not found; install Codex or run without --codex to generate its MCP configuration")
    claude_executable = _claude_executable() if args.claude else None
    if args.claude and not claude_executable:
        raise RuntimeError("Claude Code CLI was not found; install Claude Code or run without --claude")
    records = _codex_servers(executable) if args.codex else []
    if args.claude:
        records += _claude_servers()
    profile_file = None
    if args.attach:
        token = validate_token_path(args.token_file).read_text().strip()
        profile = {"url": validate_origin(args.attach), "token": token}
        if args.url:
            profile["browserUrl"] = validate_origin(args.url)
        profile_file = save_connection(profile).resolve()
    elif args.auto or args.codex or args.claude:
        profile_file = discover_connection_profile()
    profile = load_connection(profile_file) if profile_file else None
    if profile_file and args.url and not args.attach:
        profile = {**profile, "browserUrl": validate_origin(args.url)}
        save_connection(profile, profile_file)
    root = Path(__file__).resolve().parent
    destination = Path.home() / ".local/share/android-browser-bridge"
    config_path = destination / "mcp-config.json"
    existing = _generated_config()
    bindings = _native_bindings([*existing.get("mcpServers", {}).values(), *records], profile)
    target = _install_package(root, destination)
    existing_connection = profile_file is not None
    if args.codex or args.claude:
        profile_file = ensure_persistent_broker(target, args, profile_file)
        profile = load_connection(profile_file)
    command_args = [str(target)]
    if profile_file:
        command_args += ["--connection-file", str(profile_file)]
    else:
        command_args += ["--listen", args.listen, "--port", str(args.port if args.port is not None else 8766)]
        if args.url:
            command_args += ["--url", args.url]
    server_config = {"command": sys.executable, "args": command_args}
    if bindings:
        server_config["env"] = bindings
    # Re-read after building to preserve settings edited during installation.
    existing = _generated_config()
    generated_name = _server_name(existing.get("mcpServers", {}))
    config = {**existing, "mcpServers": {**existing.get("mcpServers", {}), generated_name: server_config}}
    _write_config(config_path, config)
    if args.codex:
        servers = {record["name"]: record for record in records if "name" in record}
        name = _server_name(servers)
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
        _backup(codex_home / "config.toml")
        command = [executable, "mcp", "add", name]
        for key, value in sorted(bindings.items()):
            command += ["--env", f"{key}={value}"]
        command += ["--", sys.executable, *command_args]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError("Codex MCP registration failed; the previous private configuration backup is preserved")
        from agent_integration import install_codex_guidance
        guidance = install_codex_guidance()
        guidance_installed = isinstance(guidance, dict) and bool(guidance)
        print(f"Codex MCP registered: {name}. " + ("Existing browser connection reused." if existing_connection else "Persistent broker ready for initial browser pairing.") + (" Browser task guidance installed." if guidance_installed else ""))
    if args.claude:
        name = register_claude(server_config)
        from agent_integration import install_claude_guidance
        install_claude_guidance()
        print(f"Claude Code MCP registered: {name}. Persistent broker ready. Browser task guidance installed.")
    if not args.codex and not args.claude:
        print(json.dumps({"mcpServers": {generated_name: server_config}}, indent=2))
        print(f"Config saved to {config_path}; merge this server into your MCP client's existing configuration.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
