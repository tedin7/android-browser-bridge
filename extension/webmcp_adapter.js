/* Optional fixed WebMCP consumer. Never eval or install page-defined bridges.
 * Official API: https://developer.chrome.com/docs/ai/webmcp/imperative-api
 * config MUST originate in trusted extension settings, never command arguments.
 */
(() => {
  const localErrors = new WeakSet();
  const error = (code, message, actionMayHaveOccurred = false) => {
    const failure = Object.assign(Error(message), {code, actionMayHaveOccurred, nextSteps: ["Use the fixed DOM controls when WebMCP is unavailable; do not repeat an uncertain invocation."]});
    localErrors.add(failure); return failure;
  };
  const fields = new Set(["type", "properties", "required", "additionalProperties", "items", "enum", "description", "title", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"]);
  const canonical = value => JSON.stringify(value, function(key, item) {
    return item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.keys(item).sort().map(name => [name, item[name]])) : item;
  });
  function validate(schema, value, depth = 0, schemaOnly = false) {
    if (depth > 12 || !schema || typeof schema !== "object" || Array.isArray(schema) || Object.keys(schema).some(key => !fields.has(key))) throw error("WEBMCP_SCHEMA_UNSUPPORTED", "Schema exceeds the supported fixed subset");
    const type = schema.type;
    if (type !== undefined && !["object", "array", "string", "number", "integer", "boolean", "null"].includes(type)) throw error("WEBMCP_SCHEMA_UNSUPPORTED", "Unsupported schema type");
    if (schema.enum !== undefined && (!Array.isArray(schema.enum) || schema.enum.length > 100)) throw error("WEBMCP_SCHEMA_UNSUPPORTED", "Invalid enum");
    if (schema.required !== undefined && (!Array.isArray(schema.required) || schema.required.some(key => typeof key !== "string"))) throw error("WEBMCP_SCHEMA_UNSUPPORTED", "Invalid required fields");
    if (schema.additionalProperties !== undefined && typeof schema.additionalProperties !== "boolean") throw error("WEBMCP_SCHEMA_UNSUPPORTED", "Only boolean additionalProperties is supported");
    for (const key of ["minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"]) if (schema[key] !== undefined && (typeof schema[key] !== "number" || !Number.isFinite(schema[key]) || (!["minimum", "maximum"].includes(key) && (!Number.isInteger(schema[key]) || schema[key] < 0)))) throw error("WEBMCP_SCHEMA_UNSUPPORTED", "Invalid schema bound");
    if (schema.properties !== undefined && (!schema.properties || typeof schema.properties !== "object" || Array.isArray(schema.properties))) throw error("WEBMCP_SCHEMA_UNSUPPORTED", "Invalid properties");
    for (const child of Object.values(schema.properties || {})) validate(child, undefined, depth + 1, true);
    if (schema.items !== undefined) validate(schema.items, undefined, depth + 1, true);
    if (schemaOnly) return;
    const matches = type === undefined || (type === "null" ? value === null : type === "array" ? Array.isArray(value) : type === "object" ? value !== null && typeof value === "object" && !Array.isArray(value) : type === "integer" ? Number.isInteger(value) : typeof value === type);
    if (!matches || schema.enum && !schema.enum.some(item => canonical(item) === canonical(value))) throw error("WEBMCP_INVALID_INPUT", "Input does not match the tool schema");
    if (typeof value === "number" && (!Number.isFinite(value) || schema.minimum !== undefined && value < schema.minimum || schema.maximum !== undefined && value > schema.maximum)) throw error("WEBMCP_INVALID_INPUT", "Number outside schema bounds");
    if (typeof value === "string" && (schema.minLength !== undefined && [...value].length < schema.minLength || schema.maxLength !== undefined && [...value].length > schema.maxLength)) throw error("WEBMCP_INVALID_INPUT", "String outside schema bounds");
    if (Array.isArray(value)) {
      if (schema.minItems !== undefined && value.length < schema.minItems || schema.maxItems !== undefined && value.length > schema.maxItems) throw error("WEBMCP_INVALID_INPUT", "Array outside schema bounds");
      if (schema.items) for (const item of value) validate(schema.items, item, depth + 1);
    } else if (value && typeof value === "object") {
      if ((schema.required || []).some(key => !Object.hasOwn(value, key))) throw error("WEBMCP_INVALID_INPUT", "Missing required input");
      for (const [key, item] of Object.entries(value)) {
        if (Object.hasOwn(schema.properties || {}, key)) validate(schema.properties[key], item, depth + 1);
        else if (schema.additionalProperties === false) throw error("WEBMCP_INVALID_INPUT", "Unexpected input field");
      }
    }
  }
  function createWebMCPAdapter(doc, frameWindow, config = {}) {
    const origin = doc.location?.origin;
    const allowed = config.enabled === true && Array.isArray(config.allowedOrigins) && config.allowedOrigins.includes(origin);
    const api = doc.modelContext;
    const native = typeof api?.getTools === "function" && typeof api?.executeTool === "function";
    function probe() { return {experimental: true, enabled: allowed, nativeConsumerAPI: native, supported: allowed && native, fallback: "DOM", documentOrigin: origin || null, currentFrameOnly: true}; }
    function authorize() {
      if (!allowed) throw error("WEBMCP_DISABLED", "WebMCP is disabled or the document origin is not authorized");
      if (!native) throw error("WEBMCP_UNSUPPORTED", "Native WebMCP consumer API is unavailable in this document");
    }
    async function bounded(run, timeoutMs, mayAct) {
      if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60000) throw error("WEBMCP_INVALID_INPUT", "Timeout must be 1–60000 ms");
      const controller = new AbortController(); let timer;
      try { return await Promise.race([Promise.resolve().then(() => run(controller.signal)), new Promise((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(error("WEBMCP_TIMEOUT", "WebMCP deadline exceeded", mayAct)); }, timeoutMs); })]); }
      catch (failure) { if (localErrors.has(failure)) throw failure; throw error("WEBMCP_FAILED", "Native WebMCP request failed", mayAct); }
      finally { clearTimeout(timer); }
    }
    async function tools() {
      authorize();
      const found = await bounded(() => api.getTools(), 5000, false);
      if (!Array.isArray(found) || found.length > 500) throw error("WEBMCP_LIMIT", "Tool list exceeds supported bounds");
      return found.filter(tool => tool && tool.origin === origin && tool.window === frameWindow && typeof tool.name === "string" && config.allowedToolNames?.includes(tool.name));
    }
    async function discover() {
      const found = await tools();
      return {capability: probe(), tools: found.slice(0, 50).map(tool => {
        const encoded = canonical(tool.inputSchema);
        if (!encoded || encoded.length > 16384) throw error("WEBMCP_LIMIT", "Tool schema exceeds supported bounds");
        validate(tool.inputSchema, undefined, 0, true);
        return {name: tool.name.slice(0, 128), description: String(tool.description || "").slice(0, 512), origin, inputSchema: JSON.parse(encoded), untrusted: true};
      }), truncated: found.length > 50};
    }
    async function invoke({name, input, expectedSchema, timeoutMs = 15000}) {
      const found = (await tools()).filter(tool => tool.name === name);
      if (found.length !== 1) throw error("WEBMCP_TARGET_UNAVAILABLE", "Expected one authorized tool in this frame");
      const tool = found[0], encoded = canonical(input), schema = canonical(tool.inputSchema);
      if (!encoded || encoded.length > 65536 || !schema || schema.length > 16384) throw error("WEBMCP_LIMIT", "Input or schema exceeds supported bounds");
      if (canonical(expectedSchema) !== schema) throw error("WEBMCP_SCHEMA_CHANGED", "Tool schema changed; inspect before invoking");
      const values = JSON.parse(encoded);
      validate(tool.inputSchema, values);
      if (typeof config.beforeInvoke === "function") await config.beforeInvoke(name);
      const result = await bounded(signal => api.executeTool(tool, values, {signal}), timeoutMs, true);
      if (result === null) return {state: "unknown", actionMayHaveOccurred: true, reason: "navigation", untrusted: true};
      const output = canonical(result);
      if (!output || output.length > 16384) return {state: "executed", outputOmitted: true, actionMayHaveOccurred: true, untrusted: true};
      return {state: "executed", result: JSON.parse(output), applicationVerified: false, untrusted: true};
    }
    return Object.freeze({probe, discover, invoke});
  }
  globalThis.createWebMCPAdapter = createWebMCPAdapter;
})();
