/* Fixed JSON Schema subset shared with operation_registry.py; no evaluation. */
function validateSchema(schema, value, path) {
  const fail = message => { const error = Error(`${path}: ${message}`); error.code = 'INVALID_ARGUMENT'; throw error; };
  const object = value !== null && typeof value === 'object' && !Array.isArray(value);
  const types = {object, array: Array.isArray(value), string: typeof value === 'string', boolean: typeof value === 'boolean',
    integer: Number.isInteger(value), number: typeof value === 'number' && Number.isFinite(value), null: value === null};
  if (schema.type && !(Array.isArray(schema.type) ? schema.type : [schema.type]).some(type => types[type])) fail('invalid type');
  if (typeof value === 'string' && (Array.from(value).length < (schema.minLength ?? 0) || Array.from(value).length > (schema.maxLength ?? Infinity) || (schema.pattern && !new RegExp(schema.pattern).test(value)))) fail('invalid string');
  if (schema.enum && !schema.enum.some(item => JSON.stringify(item) === JSON.stringify(value))) fail('unsupported value');
  if (typeof value === 'number' && (!Number.isFinite(value) || value < (schema.minimum ?? -Infinity) || value > (schema.maximum ?? Infinity))) fail('outside allowed range');
  if (object) {
    const properties = schema.properties || {};
    if ((schema.required || []).some(key => !Object.prototype.hasOwnProperty.call(value, key))) fail('missing required field');
    for (const key of Object.keys(value)) {
      if (Object.prototype.hasOwnProperty.call(properties, key)) validateSchema(properties[key], value[key], `${path}.${key}`);
      else if (schema.additionalProperties === false) fail('unknown field');
    }
  }
  if (Array.isArray(value)) {
    if (value.length < (schema.minItems ?? 0) || value.length > (schema.maxItems ?? Infinity)) fail('invalid item count');
    for (const item of value) validateSchema(schema.items || {}, item, `${path}[]`);
  }
  for (const key of ['anyOf', 'oneOf']) if (schema[key]) {
    let matches = 0;
    for (const alternative of schema[key]) { try { validateSchema(alternative, value, path); matches++; } catch (_) {} }
    if (!matches || (key === 'oneOf' && matches !== 1)) fail('invalid alternatives');
  }
}
function contract(operation) {
  if (!Object.prototype.hasOwnProperty.call(catalog.operations, operation)) { const error = Error('Unsupported operation'); error.code = 'INVALID_ARGUMENT'; throw error; }
  return catalog.operations[operation];
}
function validateArguments(operation, args = {}, platform) {
  const spec = contract(operation);
  if (platform && !spec.platforms.includes(platform)) throw Error('Operation unavailable on this platform');
  validateSchema(spec.inputSchema, args, 'args');
  if (operation === 'batch') {
    const inherited = {};
    for (const key of ['tabId', 'workflowId', 'leaseGeneration']) if (args[key] !== undefined) inherited[key] = args[key];
    for (const step of args.steps) validateArguments(step.op, {...inherited, ...step.args}, platform);
  }
  return args;
}
function validateResult(operation, result) {
  validateSchema(contract(operation).outputSchema, result, 'result');
  if (operation === 'batch') for (const step of result.results) validateResult(step.op, step.result);
  return result;
}
globalThis.BrowserBridgeOperations = Object.freeze({...catalog, validateArguments, validateResult});
