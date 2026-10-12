"""Device-scoped client credentials. Raw tokens are returned only at creation."""
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_CLIENT_ID = re.compile(r"^client_[a-f0-9]{32}$")


class ClientCredentials:
    def __init__(self, path=None, max_clients=1024):
        if not isinstance(max_clients, int) or isinstance(max_clients, bool) or max_clients < 1:
            raise ValueError("max_clients must be positive")
        self.path = Path(path) if path is not None else None
        self.max_clients = max_clients
        self._lock = threading.RLock()
        self._memory = {"version": 1, "clients": {}}

    @staticmethod
    def _devices(devices):
        if not isinstance(devices, (list, tuple)) or not 1 <= len(devices) <= 128:
            raise ValueError("A nonempty allowlist of at most 128 devices is required")
        if any(not isinstance(device, str) or not _ID.fullmatch(device) for device in devices):
            raise ValueError("Invalid device identifier")
        return sorted(set(devices))

    @staticmethod
    def _validate(data):
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("clients"), dict):
            raise ValueError("Invalid client credential store")
        for identifier, entry in data["clients"].items():
            if not _CLIENT_ID.fullmatch(identifier) or not isinstance(entry, dict):
                raise ValueError("Invalid client credential record")
            if not isinstance(entry.get("hash"), str) or not re.fullmatch(r"[a-f0-9]{64}", entry["hash"]):
                raise ValueError("Invalid credential hash")
            ClientCredentials._devices(entry.get("devices"))
        return data

    def _read(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return {"version": 1, "clients": {}}
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            # Bound corrupted or unexpectedly replaced configuration files.
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("Client credential store exceeds size limit")
        return self._validate(json.loads(raw))

    def _write(self, data):
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"
        if len(encoded.encode("utf-8")) > 4 * 1024 * 1024:
            raise ValueError("Client credential store exceeds size limit")
        fd, temporary = tempfile.mkstemp(prefix="." + self.path.name + "-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @contextmanager
    def _transaction(self, write=False):
        with self._lock:
            if self.path is None:
                yield self._memory
                return
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            lock_fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                os.fchmod(lock_fd, 0o600)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                data = self._read()
                yield data
                if write:
                    self._write(data)
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    def register(self, devices):
        allowed = self._devices(devices)
        with self._transaction(write=True) as data:
            if len(data["clients"]) >= self.max_clients:
                raise ValueError("Client credential limit reached")
            identifier = "client_" + secrets.token_hex(16)
            token = "abb_client_" + secrets.token_urlsafe(32)
            data["clients"][identifier] = {"hash": hashlib.sha256(token.encode("ascii")).hexdigest(), "devices": allowed}
        return {"clientId": identifier, "token": token, "devices": allowed[:]}

    def authenticate(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"abb_client_[A-Za-z0-9_-]{43}", token):
            return None
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        match = None
        with self._transaction() as data:
            for identifier, entry in data["clients"].items():
                if hmac.compare_digest(digest, entry["hash"]):
                    match = {"clientId": identifier, "devices": entry["devices"][:]}
        return match

    def revoke(self, client_id):
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            raise ValueError("Invalid client identifier")
        with self._transaction(write=True) as data:
            return data["clients"].pop(client_id, None) is not None

    def list_clients(self):
        with self._transaction() as data:
            return [{"clientId": identifier, "devices": entry["devices"][:]} for identifier, entry in data["clients"].items()]
