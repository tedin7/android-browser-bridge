/* Shared, fixed connection schema. Credentials remain in extension-local storage. */
function validateBridgeConnection(profile, index = 0) {
  if (!profile || typeof profile !== "object" || Array.isArray(profile)) throw Error("Collegamento non valido");
  const id = profile.id || "connection-" + index;
  if (typeof id !== "string" || !/^[a-zA-Z0-9_-]{1,80}$/.test(id)) throw Error("Identificatore collegamento non valido");
  const url = validateBridgeOrigin(profile.url);
  if (typeof profile.token !== "string" || !profile.token || profile.token.length > 4096 || /[^\x21-\x7e]/.test(profile.token)) throw Error("Credenziale collegamento non valida: ripeti l'abbinamento");
  if (typeof profile.device !== "string" || !/^[a-zA-Z0-9_-]{1,64}$/.test(profile.device)) throw Error("Dispositivo collegamento non valido");
  if (profile.urls !== undefined && (!Array.isArray(profile.urls) || profile.urls.length > 5)) throw Error("Indirizzi alternativi non validi");
  const urls = [...new Set([url, ...(profile.urls || []).map(validateBridgeOrigin)])];
  if (urls.length > 5) throw Error("Al massimo cinque indirizzi per lo stesso servizio");
  if (profile.enabled !== undefined && typeof profile.enabled !== "boolean") throw Error("Stato collegamento non valido");
  const name = profile.name || new URL(url).host;
  if (typeof name !== "string" || name.length > 120 || /[\x00-\x1f]/.test(name)) throw Error("Nome collegamento non valido");
  return {id, name, url, urls, token: profile.token, device: profile.device, enabled: profile.enabled !== false};
}
function normalizeBridgeConnections(storage) {
  let profiles;
  if (storage.connections !== undefined) {
    if (!Array.isArray(storage.connections) || storage.connections.length > 16) throw Error("Elenco collegamenti non valido: massimo sedici servizi");
    profiles = storage.connections.map(validateBridgeConnection);
  } else if (storage.url && storage.token && storage.device) {
    profiles = [validateBridgeConnection({...storage, id: "legacy", name: "Collegamento esistente", enabled: true})];
  } else profiles = [];
  if (new Set(profiles.map(profile => profile.id)).size !== profiles.length) throw Error("Identificatori dei collegamenti duplicati");
  return profiles;
}
function bridgeConnectionStatus(profile, runtime) {
  return {id: profile.id, name: profile.name, url: profile.url, device: profile.device, enabled: profile.enabled,
    connected: !!runtime?.connected, error: runtime?.error || "", endpoint: runtime?.endpoint || ""};
}
