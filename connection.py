"""Private, portable connection profile shared by installers and MCP launchers."""
import ipaddress
import json
import os
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def connection_path():
    configured = os.environ.get("BROWSER_BRIDGE_CONNECTION_FILE")
    if configured:
        return Path(configured).expanduser()
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    return state / "android-browser-bridge" / "connection.json"


def validate_origin(origin):
    if not isinstance(origin, str) or any(ord(character) < 33 for character in origin):
        raise ValueError("Connection URL must be an HTTP(S) origin without whitespace")
    parts = urlsplit(origin)
    try:
        parts.port
    except ValueError:
        raise ValueError("Connection URL contains an invalid port") from None
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
        if address and any(address in network for network in map(ipaddress.ip_network, networks) if address.version == network.version):
            return origin.rstrip("/")
    raise ValueError("Internet connections require HTTPS; HTTP is limited to trusted private networks")


def validate_connection(profile):
    if not isinstance(profile, dict):
        raise ValueError("Connection profile must be a JSON object")
    allowed = {"url", "token", "browserUrl", "device"}
    if set(profile) - allowed:
        raise ValueError("Connection profile contains unsupported fields")
    result = {"url": validate_origin(profile.get("url"))}
    token = profile.get("token")
    if not isinstance(token, str) or not token or len(token) > 4096 or any(ord(character) < 33 or ord(character) > 126 for character in token):
        raise ValueError("Connection profile requires a nonempty printable admin token")
    result["token"] = token
    if "browserUrl" in profile:
        result["browserUrl"] = validate_origin(profile["browserUrl"])
    if "device" in profile:
        device = profile["device"]
        if not isinstance(device, str) or not device or len(device) > 256 or any(ord(character) < 32 for character in device):
            raise ValueError("Connection profile device must be a nonempty identifier")
        result["device"] = device
    return result


def load_connection(path=None):
    """Load an existing owner-private regular file without creating credentials."""
    target = Path(path).expanduser() if path is not None else connection_path()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(target, flags)
    except FileNotFoundError:
        raise ValueError("Connection profile does not exist; configure the existing broker first") from None
    except OSError:
        raise ValueError("Connection profile must be an accessible private regular file") from None
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Connection profile must be a regular file")
        if os.name == "posix" and (metadata.st_mode & 0o077 or metadata.st_uid != os.geteuid()):
            raise ValueError("Connection profile must belong to this user with permissions 600")
        data = stream.read(16385)
    if len(data) > 16384:
        raise ValueError("Connection profile is too large")
    try:
        profile = json.loads(data)
    except (ValueError, UnicodeError):
        raise ValueError("Connection profile must contain valid JSON") from None
    return validate_connection(profile)


def save_connection(profile, path=None):
    """Atomically write the validated profile with private permissions."""
    profile = validate_connection(profile)
    target = Path(path).expanduser() if path is not None else connection_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".connection-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(profile, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
