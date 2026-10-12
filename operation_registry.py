"""Fixed-operation contracts shared by transports; no scripts or page evaluation.

operations.json is the editable source. Generated assets are checked by
``python3 generate_operations.py --check``. Baseline versions describe the
oldest catalog tested as a whole, not the original introduction of an operation.
"""
import copy
import json
import math
import re
from pathlib import Path

REGISTRY = json.loads(Path(__file__).with_name('operations.json').read_text())
PRODUCT_VERSION = REGISTRY['productVersion']
OPERATIONS = frozenset(REGISTRY['operations'])
PAGE_OPERATIONS = frozenset(name for name, spec in REGISTRY['operations'].items() if spec['engine'] == 'page')
BACKGROUND_OPERATIONS = OPERATIONS - PAGE_OPERATIONS
GLOBAL_OPERATIONS = frozenset(name for name, spec in REGISTRY['operations'].items() if spec['ordering'] == 'global')


def operation_contract(name):
    """Return a defensive copy so adapters cannot alter another adapter's schema."""
    if name not in OPERATIONS:
        raise ValueError('Unsupported operation')
    return copy.deepcopy(REGISTRY['operations'][name])


def _validate(schema, value, path):
    types = schema.get('type')
    if types is not None:
        types = types if isinstance(types, list) else [types]
        matches = {
            'null': value is None, 'object': isinstance(value, dict), 'array': isinstance(value, list),
            'string': isinstance(value, str), 'boolean': isinstance(value, bool),
            'integer': isinstance(value, int) and not isinstance(value, bool),
            'number': isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        }
        if not any(matches.get(kind, False) for kind in types):
            raise ValueError(path + ': invalid type')
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', float('inf')) or ('pattern' in schema and re.search(schema['pattern'], value) is None):
            raise ValueError(path + ': invalid string')
    if 'enum' in schema:
        def equal(candidate):
            if isinstance(value, bool) != isinstance(candidate, bool):
                return False
            return value == candidate
        if not any(equal(candidate) for candidate in schema['enum']):
            raise ValueError(path + ': unsupported value')
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if not math.isfinite(value) or ('minimum' in schema and value < schema['minimum']) or ('maximum' in schema and value > schema['maximum']):
            raise ValueError(path + ': outside allowed range')
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        if any(key not in value for key in schema.get('required', [])):
            raise ValueError(path + ': missing required field')
        if schema.get('additionalProperties') is False and any(key not in properties for key in value):
            raise ValueError(path + ': unknown field')
        for key, item in value.items():
            if key in properties:
                _validate(properties[key], item, path + '.' + key)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')):
            raise ValueError(path + ': invalid item count')
        for item in value:
            _validate(schema.get('items', {}), item, path + '[]')
    for keyword in ('anyOf', 'oneOf'):
        if keyword not in schema:
            continue
        matches = 0
        for alternative in schema[keyword]:
            try:
                _validate(alternative, value, path)
                matches += 1
            except ValueError:
                pass
        if matches == 0 or (keyword == 'oneOf' and matches != 1):
            keys = [alternative['required'][0] for alternative in schema[keyword] if list(alternative) == ['required'] and len(alternative['required']) == 1]
            if len(keys) == len(schema[keyword]):
                # Target alternatives: name the accepted fields so the caller fixes the step in one turn.
                raise ValueError(path + (': needs exactly one of ' if matches else ': needs one of ') + ', '.join(keys) + ' (invalid alternatives)')
            raise ValueError(path + ': invalid alternatives')


def validate_arguments(operation, arguments, *, platform=None):
    """Validate all batch steps before dispatch; never mutate caller arguments.

This validates structural contracts only. Backend checks still enforce current
page permissions, target uniqueness, visibility, enabled state and URL policy.
"""
    spec = operation_contract(operation)
    if platform is not None and platform not in spec['platforms']:
        raise ValueError('Operation unavailable on this platform')
    _validate(spec['inputSchema'], arguments, 'args')
    if operation == 'batch':
        inherited = {key: arguments[key] for key in ('tabId', 'workflowId', 'leaseGeneration') if key in arguments}
        for index, step in enumerate(arguments['steps']):
            try:
                validate_arguments(step['op'], {**inherited, **step.get('args', {})}, platform=platform)
            except ValueError as error:
                raise ValueError(f"steps[{index}] {step['op']}: {error}") from None
    return arguments


def validate_result(operation, result):
    """Check successful raw Firefox output before response projection; not native output."""
    _validate(operation_contract(operation)['outputSchema'], result, 'result')
    if operation == 'batch':
        for step in result['results']:
            validate_result(step['op'], step['result'])
    return result
