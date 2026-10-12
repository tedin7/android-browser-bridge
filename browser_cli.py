#!/usr/bin/env python3
"""One JSON request on stdin, one JSON response on stdout; existing private profile.

Example: echo '{"operation":"devices"}' | python3 browser_cli.py
Images are private local artifacts, never base64 in JSON output. No raw secrets,
pairing or arbitrary process execution is exposed by this adapter.
"""
import argparse
import base64
import json
import hashlib
import re
import os
from pathlib import Path
import sys
import tempfile

from operation_registry import REGISTRY

TOOL_NAMES = {'step':'browser_step','observe':'browser_observe','task':'browser_task','contract':'browser_contract','command': 'browser_command', 'status': 'browser_status',
              'devices': 'browser_devices', 'metrics': 'browser_metrics'}
MAX_REQUEST_BYTES = 1024 * 1024


def validate_request(request):
    if not isinstance(request, dict) or set(request) - {'operation', 'arguments'}:
        raise ValueError('Request requires operation and optional arguments')
    operation, arguments = request.get('operation'), request.get('arguments', {})
    if operation not in {*TOOL_NAMES, 'discover', 'artifact'} or not isinstance(arguments, dict):
        raise ValueError('Unsupported operation or invalid arguments')
    if operation in ('discover', 'devices', 'metrics') and arguments:
        raise ValueError('This operation accepts no arguments')
    if operation == 'command' and (not isinstance(arguments.get('device'), str) or not arguments['device'] or not isinstance(arguments.get('op'), str)):
        raise ValueError('Command requires explicit device and op')
    if operation == 'artifact':
        if set(arguments) != {'device', 'artifactId', 'output'} or not isinstance(arguments.get('device'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', arguments['device']) or not isinstance(arguments.get('artifactId'), str) or not re.fullmatch(r'[a-f0-9]{64}', arguments['artifactId']) or not isinstance(arguments.get('output'), str) or not arguments['output'] or arguments['output'] == '-':
            raise ValueError('Artifact requires device, artifactId and explicit output file')
    return operation, arguments


def artifact_response(result, artifact_directory=None):
    """Preserve MCP structured envelope while lifting images to private files."""
    output = {key: value for key, value in result.items() if key != 'content'}
    output['content'] = []
    directory = None
    for block in result.get('content', []):
        if block.get('type') != 'image':
            output['content'].append(block)
            continue
        mime = block.get('mimeType')
        if mime not in ('image/png', 'image/jpeg'):
            raise ValueError('Unsupported image type')
        data = base64.b64decode(block['data'], validate=True)
        if not data or len(data) > 32 * 1024 * 1024:
            raise ValueError('Invalid image size')
        if directory is None:
            if artifact_directory is not None:
                parent = Path(artifact_directory)
                parent.mkdir(parents=True, exist_ok=True)
                directory = Path(tempfile.mkdtemp(prefix='browser-bridge-', dir=parent))
            else:
                directory = Path(tempfile.mkdtemp(prefix='browser-bridge-artifacts-'))
        fd, filename = tempfile.mkstemp(suffix='.png' if mime == 'image/png' else '.jpg', dir=directory)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        output['content'].append({'type': 'artifact', 'mimeType': mime, 'path': filename, 'bytes': len(data)})
    return output


def download_artifact(arguments, transport=None):
    if transport is None:
        from connection import load_connection
        from bridge import api
        profile = load_connection()
        transport = lambda data: api(profile['url'], profile['token'], '/api/native-artifacts/get', data)
    result = transport({'device': arguments['device'], 'artifactId': arguments['artifactId']})
    encoded = result.get('dataBase64')
    if not isinstance(encoded, str) or len(encoded) > 2*1024*1024:
        raise ValueError('Artifact response exceeds size limit')
    data = base64.b64decode(encoded, validate=True)
    if len(data) > 1024*1024 or len(data) != result.get('size') or hashlib.sha256(data).hexdigest() != result.get('sha256') or result.get('device') != arguments['device'] or result.get('artifactId') != arguments['artifactId']:
        raise ValueError('Artifact identity or integrity mismatch')
    destination = Path(arguments['output']).expanduser().absolute()
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {'artifactId': arguments['artifactId'], 'device': arguments['device'], 'path': str(destination), 'bytes': len(data), 'sha256': result['sha256']}


def execute(request, client_factory=None, artifact_directory=None, artifact_transport=None):
    operation, arguments = validate_request(request)
    if operation == 'discover':
        return {'adapterVersion': 1, 'operations': sorted([*TOOL_NAMES, 'discover', 'artifact']),
                'registryVersion': REGISTRY['registryVersion'], 'productVersion': REGISTRY['productVersion'],
                'browserOperations': REGISTRY['operations']}
    if operation == 'artifact':
        return download_artifact(arguments, artifact_transport)
    if client_factory is None:
        from profile_client import Client
        client_factory = Client
    client = client_factory()
    try:
        result = client.rpc('tools/call', {'name': TOOL_NAMES[operation], 'arguments': arguments})
        return artifact_response(result, artifact_directory)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-dir', help='Parent directory for private image artifacts; caller removes them when finished')
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError('Request too large')
        request = json.loads(raw)
        result = execute(request, artifact_directory=args.artifact_dir)
    except Exception as error:
        # Do not reflect untrusted request text, environment or child stderr.
        result = {'isError': True, 'error': {'code': 'CLI_REQUEST_FAILED', 'errorType': type(error).__name__,
                   'message': 'Request failed. Check the request schema and installed private Browser Bridge profile; reconcile any action before repeating it.'}}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    return 1 if result.get('isError') else 0


if __name__ == '__main__':
    raise SystemExit(main())
