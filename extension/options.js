/* Opt-in pairing UI. Only fixed pairing requests; credentials never enter markup. */
const language = navigator.language?.toLowerCase().startsWith("it") ? "it" : "en";
const messages = {
  it: {
    paused:"In pausa", active:"Controllo attivo", eyebrow:"IL TUO BROWSER, SOTTO IL TUO CONTROLLO", headline:"Il tuo browser. I tuoi terminali.",
    intro:"Collega Firefox ai tuoi assistenti su Linux. Aggiungi più server e scegli quando possono interagire con le tue schede.",
    addTitle:"Aggiungi un collegamento", addSubtitle:"Il codice arriva dal tuo assistente o terminale.", step1:"Chiedi al tuo assistente di collegare questo browser.", step2:"Incolla qui il codice BB1 e autorizza il controllo.",
    nameLabel:"Nome del collegamento", namePlaceholder:"Es. il mio portatile", optionalName:"Facoltativo: scegli un nome facile da riconoscere.", codeLabel:"Codice di collegamento", codeHelp:"È monouso e scade dopo pochi minuti. Non condividere il codice.",
    advanced:"Ho un codice breve", originLabel:"Indirizzo del servizio", originHelp:"Serve solo per un codice senza il prefisso BB1. Usa l’indirizzo fornito dal tuo assistente.",
    consentTitle:"Autorizzo questo collegamento", consentBody:"Questo server e il suo assistente potranno leggere e controllare le mie schede, anche su altri siti, e richiedere contenuti e screenshot. Le pagine possono contenere dati sensibili.", addButton:"Collega questo browser ↗",
    connectionsTitle:"I tuoi collegamenti", resumeAll:"Riprendi controllo", pauseAll:"Sospendi tutto", pauseBanner:"Il controllo è in pausa. I collegamenti salvati restano disponibili.",
    emptyTitle:"Tutto parte da un collegamento.", emptyBody:"Aggiungi il primo server. Potrai collegarne altri senza scollegare quello già presente.",
    controlNote:"Hai sempre l’ultima parola: metti in pausa un server, rimuovilo o sospendi tutto il controllo con un tocco. Un’azione già avviata potrebbe completarsi.",
    footer:"Il controllo parte solo con la tua autorizzazione.", privacy:"Privacy e dati trasferiti", legacyName:"Collegamento esistente", connected:"Collegato", waiting:"In attesa", unavailable:"Da verificare", resume:"Riprendi", pause:"Metti in pausa", remove:"Rimuovi",
    device:"Browser: ", countOne:"1 collegamento salvato", countMany:"{count} collegamenti salvati", waitingHelp:"Il collegamento è salvato. Il servizio deve essere acceso e raggiungibile dal browser.", offlineHelp:"Controlla che il servizio sia acceso e che questo dispositivo abbia accesso alla sua rete. Gli altri collegamenti restano indipendenti.", revokedHelp:"L’accesso non è più valido. Chiedi al tuo assistente un nuovo codice di collegamento.", pausedHelp:"Questo server non riceve nuovi comandi finché non riprendi il controllo.",
    connecting:"Collegamento in corso…", saved:"Collegamento aggiunto. Puoi gestirlo qui sotto.", savedPaused:"Collegamento aggiunto. Il controllo globale resta in pausa: tocca «Riprendi controllo» quando vuoi abilitarlo.", invalidCode:"Il codice non è valido. Copia il collegamento completo BB1 dal tuo assistente.", invalidOrigin:"L’indirizzo non è valido. Usa quello fornito dal tuo assistente: HTTPS su Internet o HTTP su una rete privata fidata.", invalidName:"Scegli un nome di massimo 64 caratteri, senza interruzioni di riga.", consentRequired:"Per collegare questo server devi prima autorizzarne il controllo.", maxConnections:"Puoi salvare fino a 16 collegamenti. Rimuovine uno prima di aggiungere un altro server.", expired:"Il codice è scaduto o è già stato usato. Chiedi al tuo assistente un nuovo collegamento.", networkError:"Il servizio non è raggiungibile. Verifica che sia acceso e che il browser possa raggiungerlo, poi riprova.", pairError:"Il servizio non ha completato il collegamento. Chiedi al tuo assistente un nuovo codice.", invalidReply:"Il servizio ha restituito un collegamento non valido. Chiedi al tuo assistente di verificarlo e di creare un nuovo codice.", storageError:"Non è stato possibile salvare il collegamento. Quelli già salvati restano disponibili. Il codice potrebbe essere stato usato: chiedine uno nuovo prima di riprovare.", configError:"Non è stato possibile leggere i collegamenti salvati. Riapri le impostazioni; nessuna credenziale è stata sostituita.", actionError:"Non è stato possibile aggiornare il collegamento. Riprova dopo aver riaperto le impostazioni.", replaceConfirm:"Esiste già un collegamento per questo servizio. Vuoi sostituirlo solo se il nuovo abbinamento riesce?", replaceCancelled:"Il collegamento esistente è stato mantenuto.", removeConfirm:"Rimuovere «{name}»? Questo server non potrà più controllare il browser tramite questo collegamento.", removed:"Collegamento rimosso da questo browser.", globalPaused:"Tutto il controllo è in pausa. Un’azione già avviata potrebbe completarsi.", globalResumed:"Controllo ripreso per i collegamenti abilitati.", cleanupWarning:"Impostazioni salvate. Riapri questa pagina per completare la pulizia dei vecchi campi."
  },
  en: {
    paused:"Paused", active:"Control enabled", eyebrow:"YOUR BROWSER, YOUR CONTROL", headline:"Your browser. Your terminals.",
    intro:"Connect Firefox to your Linux assistants. Add multiple servers and choose when they can interact with your tabs.", addTitle:"Add a connection", addSubtitle:"Get the code from your assistant or terminal.", step1:"Ask your assistant to connect this browser.", step2:"Paste the BB1 code here and authorize control.",
    nameLabel:"Connection name", namePlaceholder:"For example, my laptop", optionalName:"Optional: choose a name you will recognize.", codeLabel:"Connection code", codeHelp:"It is single-use and expires after a few minutes. Keep the code private.", advanced:"I have a short code", originLabel:"Service address", originHelp:"Only needed for codes without the BB1 prefix. Use the address supplied by your assistant.",
    consentTitle:"I authorize this connection", consentBody:"This server and its assistant may read and control my tabs, including other websites, and request page content and screenshots. Pages may contain sensitive data.", addButton:"Connect this browser ↗", connectionsTitle:"Your connections", resumeAll:"Resume control", pauseAll:"Pause all", pauseBanner:"Control is paused. Your saved connections remain available.",
    emptyTitle:"It starts with one connection.", emptyBody:"Add your first server. You can connect others without disconnecting the one already here.", controlNote:"You stay in control: pause a server, remove it, or pause all control with one tap. An action already started may still complete.", footer:"Control starts only with your permission.", privacy:"Privacy and transferred data", legacyName:"Existing connection", connected:"Connected", waiting:"Waiting", unavailable:"Needs attention", resume:"Resume", pause:"Pause", remove:"Remove",
    device:"Browser: ", countOne:"1 saved connection", countMany:"{count} saved connections", waitingHelp:"Your connection is saved. Its service must be running and reachable from this browser.", offlineHelp:"Check that the service is running and this device can reach its network. Other connections remain independent.", revokedHelp:"Access is no longer valid. Ask your assistant for a new connection code.", pausedHelp:"This server will not receive new commands until you resume control.",
    connecting:"Connecting…", saved:"Connection added. Manage it below.", savedPaused:"Connection added. Global control stays paused: tap “Resume control” when you want to enable it.", invalidCode:"That code is invalid. Copy the complete BB1 connection from your assistant.", invalidOrigin:"That address is invalid. Use the one provided by your assistant: HTTPS on the Internet or HTTP on a trusted private network.", invalidName:"Choose a name of up to 64 characters, without line breaks.", consentRequired:"Authorize this server’s control before connecting it.", maxConnections:"You can save up to 16 connections. Remove one before adding another server.", expired:"The code has expired or was already used. Ask your assistant for a new connection.", networkError:"The service is unreachable. Check that it is running and this browser can reach it, then try again.", pairError:"The service could not complete pairing. Ask your assistant for a new code.", invalidReply:"The service returned an invalid connection. Ask your assistant to check it and create a new code.", storageError:"The connection could not be saved. Existing saved connections remain available. The code may have been used: request a new one before retrying.", configError:"Saved connections could not be read. Reopen settings; no credentials were replaced.", actionError:"The connection could not be updated. Reopen settings and try again.", replaceConfirm:"A connection to this service already exists. Replace it only if the new pairing succeeds?", replaceCancelled:"Your existing connection was kept.", removeConfirm:"Remove “{name}”? This server will no longer control this browser through this connection.", removed:"Connection removed from this browser.", globalPaused:"All control is paused. An action already started may still complete.", globalResumed:"Control resumed for enabled connections.", cleanupWarning:"Settings saved. Reopen this page to finish clearing the old fields."
  }
};
const translate = key => messages[language][key] || messages.en[key] || key;
const storageFields = ["connections", "enabled", "url", "urls", "token", "device"];
const legacyFields = ["url", "urls", "token", "device"];
let state = {profiles: [], enabled: false}, busy = false, mutation = Promise.resolve();
const byId = id => document.getElementById(id);
function uiError(key) { return Object.assign(Error(translate(key)), {uiKey: key}); }
function notice(id, key, error = false) { const element = byId(id); element.textContent = translate(key); element.dataset.tone = error ? "error" : "success"; }
function initializeLanguage() {
  document.documentElement.lang = language;
  document.querySelectorAll("[data-i18n]").forEach(element => { element.textContent = translate(element.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(element => { element.placeholder = translate(element.dataset.i18nPlaceholder); });
}
async function readState() {
  const config = await browser.storage.local.get(storageFields);
  if (config.enabled !== undefined && typeof config.enabled !== "boolean") throw uiError("configError");
  return {config, profiles: normalizeBridgeConnections(config), enabled: config.enabled === true};
}
function parsePairing(value, manualOrigin) {
  let origin = manualOrigin, code = value.trim(), alternatives = [];
  if (!code || code.length > 8192) throw uiError("invalidCode");
  if (code.startsWith("BB1.")) {
    try {
      const encoded = code.slice(4).replace(/-/g, "+").replace(/_/g, "/");
      const bytes = Uint8Array.from(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "=")), character => character.charCodeAt(0));
      const bundle = JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(bytes));
      origin = bundle.url; code = bundle.code; alternatives = bundle.urls || [];
    } catch (_) { throw uiError("invalidCode"); }
  }
  if (typeof code !== "string" || !/^[a-fA-F0-9]{6}-[a-fA-F0-9]{6}$/.test(code)) throw uiError("invalidCode");
  if (!Array.isArray(alternatives) || alternatives.length > 4) throw uiError("invalidOrigin");
  let url, urls;
  try { url = validateBridgeOrigin(origin); urls = [...new Set([url, ...alternatives.map(validateBridgeOrigin)])]; }
  catch (_) { throw uiError("invalidOrigin"); }
  return {url, urls, code: code.toUpperCase()};
}
function duplicateProfile(profiles, bundle) { return profiles.find(profile => profile.urls.some(url => bundle.urls.includes(url))); }
async function pairAtEndpoints(bundle) {
  for (const endpoint of bundle.urls) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    let receivedReply = false;
    try {
      const response = await fetch(endpoint + "/api/pair", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({code: bundle.code}), signal: controller.signal, cache: "no-store"});
      receivedReply = true;
      if (response.status >= 500) continue;
      if (!response.ok) throw uiError(response.status === 400 || response.status === 404 || response.status === 409 || response.status === 410 ? "expired" : "pairError");
      try { return await response.json(); }
      catch (_) { throw Object.assign(uiError("invalidReply"), {pairConsumed: true}); }
    } catch (error) {
      if (error.uiKey) throw error;
      // Once headers arrived, do not retry a pairing whose code may already
      // have been consumed. The timer also covers the response body itself.
      if (receivedReply) throw Object.assign(uiError("invalidReply"), {pairConsumed: true});
    } finally { clearTimeout(timer); }
  }
  throw uiError("networkError");
}
function updateStorage(update) {
  const task = mutation.then(async () => {
    const current = await readState(), next = update(current);
    if (!next) return current;
    // Erase old credentials in the same write as migration. Even if deleting
    // the empty legacy keys later fails, their previous token is already gone.
    await browser.storage.local.set({connections: next.profiles, enabled: next.enabled, url: null, urls: null, token: null, device: null});
    try { await browser.storage.local.remove(legacyFields); }
    catch (_) { notice("connection-status", "cleanupWarning"); }
    await refresh();
    return next;
  });
  mutation = task.catch(() => {});
  return task;
}
async function addPairing() {
  if (busy) return;
  let paired = false;
  busy = true; byId("add").disabled = true;
  try {
    if (!byId("consent").checked) throw uiError("consentRequired");
    const name = byId("name").value.trim();
    if (name.length > 64 || /[\x00-\x1f]/.test(name)) throw uiError("invalidName");
    const bundle = parsePairing(byId("code").value, byId("url").value.trim());
    const before = await readState(), duplicate = duplicateProfile(before.profiles, bundle);
    if (before.profiles.length >= 16 && !duplicate) throw uiError("maxConnections");
    if (duplicate && !window.confirm(translate("replaceConfirm"))) { notice("form-status", "replaceCancelled"); return; }
    notice("form-status", "connecting");
    const result = await pairAtEndpoints(bundle); paired = true;
    let profile;
    try { profile = validateBridgeConnection({id: duplicate?.id || crypto.randomUUID(), name: name || new URL(bundle.url).host, url: bundle.url, urls: bundle.urls, token: result.token, device: result.device, enabled: true}); }
    catch (_) { throw uiError("invalidReply"); }
    const saved = await updateStorage(current => {
      const latestDuplicate = duplicateProfile(current.profiles, bundle);
      if (latestDuplicate && latestDuplicate.id !== duplicate?.id) throw uiError("storageError");
      if (!latestDuplicate && current.profiles.length >= 16) throw uiError("maxConnections");
      const profiles = latestDuplicate ? current.profiles.map(item => item.id === latestDuplicate.id ? profile : item) : [...current.profiles, profile];
      // Preserve an explicit global pause, including after the last removal.
      const enabled = current.config.enabled === undefined && current.profiles.length === 0 ? true : current.enabled;
      return {profiles, enabled};
    });
    byId("code").value = ""; byId("name").value = ""; byId("url").value = ""; byId("consent").checked = false;
    notice("form-status", saved.enabled ? "saved" : "savedPaused");
  } catch (error) {
    notice("form-status", error.uiKey || (paired ? "storageError" : "configError"), true);
    if (paired || error.pairConsumed) byId("code").value = "";
  } finally { busy = false; byId("add").disabled = false; }
}
async function toggleConnection(id) {
  try { await updateStorage(current => ({profiles: current.profiles.map(profile => profile.id === id ? {...profile, enabled: !profile.enabled} : profile), enabled: current.enabled})); }
  catch (_) { notice("connection-status", "actionError", true); }
}
async function removeConnection(id) {
  const current = await readState(), profile = current.profiles.find(item => item.id === id);
  if (!profile || !window.confirm(translate("removeConfirm").replace("{name}", profile.name))) return;
  try { await updateStorage(latest => ({profiles: latest.profiles.filter(item => item.id !== id), enabled: latest.enabled})); notice("connection-status", "removed"); }
  catch (_) { notice("connection-status", "actionError", true); }
}
async function toggleGlobal() {
  try {
    const updated = await updateStorage(current => ({profiles: current.profiles, enabled: !current.enabled}));
    notice("connection-status", updated.enabled ? "globalResumed" : "globalPaused");
  } catch (_) { notice("connection-status", "actionError", true); }
}
function element(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
function connectionCard(profile) {
  const card = element("article", "connection-card"); card.dataset.connection = profile.id;
  const heading = element("div", "card-heading"), details = element("div");
  details.append(element("h3", "card-name", profile.id === "legacy" && profile.name === "Collegamento esistente" ? translate("legacyName") : profile.name), element("p", "card-device", translate("device") + profile.device));
  const badge = element("span", "badge badge-muted"); badge.dataset.role = "status";
  heading.append(details, badge);
  const endpoint = element("code", "endpoint", profile.url); endpoint.dataset.role = "endpoint";
  const help = element("p", "card-help"); help.dataset.role = "help";
  const actions = element("div", "card-actions"), toggle = element("button", "button button-secondary", translate(profile.enabled ? "pause" : "resume")), remove = element("button", "button button-quiet button-danger", translate("remove"));
  toggle.type = remove.type = "button"; toggle.addEventListener("click", () => toggleConnection(profile.id)); remove.addEventListener("click", () => removeConnection(profile.id).catch(() => notice("connection-status", "actionError", true)));
  toggle.setAttribute("aria-label", translate(profile.enabled ? "pause" : "resume") + ": " + profile.name); remove.setAttribute("aria-label", translate("remove") + ": " + profile.name);
  actions.append(toggle, remove); card.append(heading, endpoint, help, actions); return card;
}
function render() {
  document.body.classList.toggle("has-connections", state.profiles.length > 0);
  byId("global-badge").textContent = translate(state.enabled ? "active" : "paused"); byId("global-badge").className = "badge" + (state.enabled ? "" : " badge-muted");
  byId("global-toggle").textContent = translate(state.enabled ? "pauseAll" : "resumeAll"); byId("global-toggle").disabled = !state.profiles.length;
  byId("connection-count").textContent = translate(state.profiles.length === 1 ? "countOne" : "countMany").replace("{count}", state.profiles.length);
  byId("pause-banner").hidden = state.enabled || !state.profiles.length; byId("empty").hidden = state.profiles.length > 0;
  byId("connections").replaceChildren(...state.profiles.map(connectionCard));
}
async function refreshStatus() {
  let status;
  try { status = await browser.runtime.sendMessage({type: "status"}); }
  catch (_) { status = {}; }
  const statuses = Array.isArray(status?.connections) ? status.connections : (state.profiles.length === 1 ? [{id: state.profiles[0].id, ...status}] : []);
  for (const card of byId("connections").children) {
    const profile = state.profiles.find(item => item.id === card.dataset.connection), remote = statuses.find(item => item.id === card.dataset.connection);
    if (!profile) continue;
    const badge = card.querySelector('[data-role="status"]'), help = card.querySelector('[data-role="help"]'), endpoint = card.querySelector('[data-role="endpoint"]');
    const paused = !state.enabled || !profile.enabled, connected = !paused && remote?.connected, failed = !paused && !!remote?.error;
    badge.textContent = translate(paused ? "paused" : connected ? "connected" : failed ? "unavailable" : "waiting"); badge.className = "badge" + (paused ? " badge-muted" : failed ? " badge-error" : connected ? "" : " badge-waiting");
    help.hidden = connected; help.textContent = translate(paused ? "pausedHelp" : failed ? (/401|403|revok/i.test(remote.error) ? "revokedHelp" : "offlineHelp") : "waitingHelp");
    let origin = profile.url;
    try { if (remote?.endpoint && profile.urls.includes(validateBridgeOrigin(remote.endpoint))) origin = remote.endpoint; } catch (_) {}
    endpoint.textContent = origin;
  }
}
async function refresh() {
  try { state = await readState(); render(); await refreshStatus(); }
  catch (_) { notice("connection-status", "configError", true); }
}
initializeLanguage();
byId("config").addEventListener("submit", event => { event.preventDefault(); addPairing(); });
byId("global-toggle").addEventListener("click", toggleGlobal);
browser.storage.onChanged.addListener((changes, area) => { if (area === "local" && storageFields.some(key => key in changes)) refresh(); });
refresh();
setInterval(() => { if (!document.hidden) refreshStatus(); }, 1500);
