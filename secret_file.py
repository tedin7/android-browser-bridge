"""Resolve `valueFile` into `value` on the server so a password never passes through the model.

The file must live in the secret directory (BROWSER_BRIDGE_SECRET_DIR, default
~/.config/browser-bridge-secrets), be a regular file owned by this user with no
group/other access, and be small. Errors never contain file contents.
"""
import os
import stat
from pathlib import Path

FILL_OPERATIONS = frozenset({'fill', 'type'})
MAX_BYTES = 1024


def secret_dir():
    return Path(os.environ.get('BROWSER_BRIDGE_SECRET_DIR') or Path.home() / '.config' / 'browser-bridge-secrets')


def read_secret(name):
    if not isinstance(name, str) or not name or '\x00' in name:
        raise ValueError('INVALID_ARGUMENT: valueFile must be a file name inside the secret directory')
    root = secret_dir().resolve()
    candidate = Path(name)
    path = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError('INVALID_ARGUMENT: valueFile must be inside the secret directory')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError('INVALID_ARGUMENT: valueFile cannot be opened') from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('INVALID_ARGUMENT: valueFile must be a regular file of this user with mode 0600')
        if info.st_size > MAX_BYTES:
            raise ValueError('INVALID_ARGUMENT: valueFile is too large')
        data = os.read(fd, MAX_BYTES + 1)
    finally:
        os.close(fd)
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('INVALID_ARGUMENT: valueFile is not UTF-8 text') from None
    return text[:-1] if text.endswith('\n') else text


def resolve_value_file(operation, values):
    """Return (values with valueFile replaced by value, secrets read). Only fill/type, also inside batch steps."""
    if operation == 'batch' and isinstance(values.get('steps'), list):
        steps, secrets = [], []
        for step in values['steps']:
            args = step.get('args') if isinstance(step, dict) else None
            if isinstance(args, dict) and 'valueFile' in args:
                resolved, found = resolve_value_file(step.get('op'), args)
                steps.append({**step, 'args': resolved})
                secrets += found
            else:
                steps.append(step)
        return ({**values, 'steps': steps} if secrets else values), secrets
    if 'valueFile' not in values:
        return values, []
    if operation not in FILL_OPERATIONS:
        raise ValueError('INVALID_ARGUMENT: valueFile is only supported by fill and type')
    if 'value' in values:
        raise ValueError('INVALID_ARGUMENT: use either value or valueFile, not both')
    secret = read_secret(values['valueFile'])
    return {**{key: item for key, item in values.items() if key != 'valueFile'}, 'value': secret}, [secret]


def scrub(data, secrets):
    """Remove any copy of a secret from a result before it reaches the model."""
    if not secrets:
        return data
    if isinstance(data, str):
        for secret in secrets:
            if secret:
                data = data.replace(secret, '[redacted]')
        return data
    if isinstance(data, list):
        return [scrub(item, secrets) for item in data]
    if isinstance(data, dict):
        return {key: scrub(item, secrets) for key, item in data.items()}
    return data
