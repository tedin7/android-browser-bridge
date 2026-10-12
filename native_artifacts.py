"""Explicit native sharing into private, device-scoped, expiring artifacts."""
import base64
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path


class NativeArtifacts:
    def __init__(self, directory, max_bytes=1024*1024, max_total=64*1024*1024,
                 ttl_seconds=86400, max_items=256, clock=time.time):
        if min(max_bytes, max_total, ttl_seconds, max_items) <= 0:
            raise ValueError('Artifact limits must be positive')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.max_bytes, self.max_total = max_bytes, max_total
        self.ttl_seconds, self.max_items, self.clock = ttl_seconds, max_items, clock
        self.lock = threading.Lock()

    @staticmethod
    def _device(device):
        if not isinstance(device, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', device):
            raise ValueError('Invalid device')

    def _metadata(self, identifier):
        fd = os.open(self.directory / (identifier + '.json'), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError('Invalid artifact metadata')
        data = json.loads(raw)
        self._device(data.get('device'))
        if data.get('artifactId') != identifier or not isinstance(data.get('expiresAt'), (float, int)) or not isinstance(data.get('size'), int) or not 0 <= data['size'] <= self.max_bytes or not re.fullmatch(r'[a-f0-9]{64}', str(data.get('sha256', ''))):
            raise ValueError('Invalid artifact metadata')
        return data

    def _cleanup(self):
        for path in self.directory.glob('*.json'):
            if not re.fullmatch(r'[a-f0-9]{64}', path.stem):
                continue
            try:
                metadata = self._metadata(path.stem)
            except (OSError, ValueError, TypeError):
                continue  # Legacy/unproven ownership is never synthesized.
            if metadata['expiresAt'] <= self.clock():
                (self.directory / (path.stem + '.bin')).unlink(missing_ok=True)
                path.unlink(missing_ok=True)

    def _write(self, destination, data):
        fd, temporary = tempfile.mkstemp(prefix='.share-', dir=self.directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _read_data(self, identifier, metadata):
        fd = os.open(self.directory / (identifier + '.bin'), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read(self.max_bytes + 1)
        if len(data) != metadata['size'] or hashlib.sha256(data).hexdigest() != metadata['sha256']:
            raise ValueError('Artifact integrity check failed')
        return data

    def save(self, device, body):
        self._device(device)
        share = body.get('shareId')
        if not isinstance(share, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', share):
            raise ValueError('Invalid shareId')
        if ('text' in body) == ('dataBase64' in body):
            raise ValueError('Exactly one share payload required')
        if 'text' in body:
            if not isinstance(body['text'], str):
                raise ValueError('Invalid text')
            data = body['text'].encode()
        else:
            if not isinstance(body['dataBase64'], str) or len(body['dataBase64']) > self.max_bytes*2:
                raise ValueError('Share too large')
            try:
                data = base64.b64decode(body['dataBase64'], validate=True)
            except Exception:
                raise ValueError('Invalid encoding') from None
        if len(data) > self.max_bytes:
            raise ValueError('Share too large')
        identifier = hashlib.sha256((device+'\0'+share).encode()).hexdigest()
        destination = self.directory / (identifier+'.bin')
        with self.lock:
            self._cleanup()
            if destination.exists():
                try:
                    metadata = self._metadata(identifier)
                except (OSError, ValueError, TypeError):
                    raise ValueError('Existing artifact ownership is unavailable') from None
                if metadata['device'] != device or self._read_data(identifier, metadata) != data:
                    raise ValueError('Share ID conflict')
                return {'artifactId': identifier, 'size': len(data)}
            retained = list(self.directory.glob('*.bin'))
            if len(retained) >= self.max_items or sum(p.stat().st_size for p in retained)+len(data) > self.max_total:
                raise ValueError('Artifact capacity reached')
            metadata = {'artifactId': identifier, 'device': device, 'size': len(data),
                        'sha256': hashlib.sha256(data).hexdigest(), 'createdAt': self.clock(),
                        'expiresAt': self.clock()+self.ttl_seconds,
                        'mimeType': 'text/plain;charset=utf-8' if 'text' in body else 'application/octet-stream'}
            self._write(destination, data)
            self._write(self.directory / (identifier+'.json'), json.dumps(metadata, separators=(',', ':')).encode())
            directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return {'artifactId': identifier, 'size': len(data)}

    def get(self, identifier, device, allowed_devices=None):
        self._device(device)
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{64}', identifier):
            raise ValueError('Invalid artifact identifier')
        if allowed_devices is not None and device not in allowed_devices:
            raise PermissionError('Artifact device outside client scope')
        with self.lock:
            self._cleanup()
            try:
                metadata = self._metadata(identifier)
            except (OSError, ValueError, TypeError):
                raise KeyError('Artifact unavailable or owner metadata missing') from None
            if metadata['device'] != device:
                raise PermissionError('Artifact belongs to another device')
            data = self._read_data(identifier, metadata)
            return {**metadata, 'dataBase64': base64.b64encode(data).decode('ascii')}
