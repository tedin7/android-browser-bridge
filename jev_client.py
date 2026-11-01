"""Minimal Jev (TypeSafe systemone) client for choices and yes/no checks.

The key comes from the environment or from a private (0600, owner-only) file.
It is never logged, returned or placed in an error message. Without a key every
function raises JevUnavailable and callers fall back to the calling model.
"""
import json
import os
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
MODEL = 'jev-latest'
KEY_ENV = 'BROWSER_BRIDGE_JEV_KEY'
KEY_FILE_ENV = 'BROWSER_BRIDGE_JEV_KEY_FILE'
# Same files that Subtask reads, so one key serves both; read in place, never copied.
DEFAULT_KEY_FILES = ('~/.config/subtask/jev/jev-key', '~/.config/typesafe/api-key', '~/.config/subtask/env')
KEY_NAME = 'TYPESAFE_API_KEY'
MAX_KEY_FILE = 16384


class JevUnavailable(RuntimeError):
    pass


def _read_private(path):
    path = Path(path).expanduser()
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > MAX_KEY_FILE:
            return None
        return os.read(descriptor, MAX_KEY_FILE).decode('utf-8', 'replace')
    finally:
        os.close(descriptor)


def _from_text(text):
    """A file holds either the bare key or NAME=value lines."""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('#')]
    for line in lines:
        name, sep, value = line.removeprefix('export ').partition('=')
        if sep and name.strip() == KEY_NAME:
            return value.strip().strip('"').strip("'")
    if len(lines) == 1 and '=' not in lines[0]:
        return lines[0]
    return None


def resolve_key(environ=None):
    environ = os.environ if environ is None else environ
    key = (environ.get(KEY_ENV) or '').strip()
    if not key:
        configured = environ.get(KEY_FILE_ENV)
        for path in ([configured] if configured else list(DEFAULT_KEY_FILES)):
            text = _read_private(path)
            key = _from_text(text) if text else None
            if key:
                break
    if not key or any(c.isspace() or not c.isprintable() for c in key):
        raise JevUnavailable('Jev key not configured')
    return key


def available(environ=None):
    try:
        resolve_key(environ)
        return True
    except JevUnavailable:
        return False


def ask(state, questions, *, opener=urllib.request.urlopen, sleep=time.sleep, environ=None, timeout=60):
    """POST one systemone request; retry only on 503. Returns the parsed JSON body."""
    key = resolve_key(environ)
    body = json.dumps({'model': MODEL, 'state': state, 'questions': questions}).encode()
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Cache-Control': 'no-store'}
    for attempt in range(3):
        request = urllib.request.Request(ENDPOINT, data=body, headers=headers)
        try:
            with opener(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code != 503 or attempt == 2:
                raise JevUnavailable('Jev request failed: HTTP %s' % error.code) from None
            sleep(1)
        except (OSError, ValueError):
            raise JevUnavailable('Jev request failed') from None
    raise JevUnavailable('Jev request failed')


def choose(state, instructions, criteria, **options):
    """Return (choice, probability) for one choice question; probability is the top one."""
    answers = ask(state, {'pick': {'type': 'choice', 'instructions': instructions, 'criteria': criteria}}, **options)
    answer = (answers.get('answers') or {}).get('pick') or {}
    probabilities = answer.get('probabilities') or {}
    return answer.get('choice'), (max(probabilities.values()) if probabilities else 0.0)


def yes_probability(state, instructions, **options):
    answers = ask(state, {'q': {'type': 'noul', 'instructions': instructions}}, **options)
    value = ((answers.get('answers') or {}).get('q') or {}).get('noul')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JevUnavailable('Jev answer malformed')
    return float(value)
