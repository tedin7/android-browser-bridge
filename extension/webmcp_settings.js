/* Shared validation for settings authored locally in the extension UI. */
(() => {
  function normalizeWebMCPSettings(value = {}) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Invalid WebMCP settings');
    const origins = value.allowedOrigins ?? [], names = value.allowedToolNames ?? [];
    if (!Array.isArray(origins) || origins.length > 16 || !Array.isArray(names) || names.length > 64) throw Error('Use at most 16 origins and 64 tool names');
    const allowedOrigins = [...new Set(origins.map(text => {
      if (typeof text !== 'string') throw Error('Origin must be a URL');
      const url = new URL(text);
      if (url.username || url.password || url.search || url.hash || url.pathname !== '/' || !(url.protocol === 'https:' || url.protocol === 'http:' && ['localhost','127.0.0.1','[::1]'].includes(url.hostname))) throw Error('Use exact HTTPS origins without paths (local HTTP is allowed)');
      return url.origin;
    }))];
    const allowedToolNames = [...new Set(names.map(name => {
      if (typeof name !== 'string' || !/^[A-Za-z0-9_.:-]{1,128}$/.test(name)) throw Error('Invalid tool name');
      return name;
    }))];
    const enabled = value.enabled === true;
    if (enabled && (!allowedOrigins.length || !allowedToolNames.length)) throw Error('Choose allowed origins and tools before enabling');
    return {enabled, allowedOrigins, allowedToolNames};
  }
  globalThis.normalizeWebMCPSettings = normalizeWebMCPSettings;
})();
