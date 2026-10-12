/* Fixed commands, resident page engine and event-driven long polling. */
const PAGE_OPERATIONS = new Set(["read", "inspect", "locate", "click", "click_point", "drag", "double_click", "hover", "focus", "fill", "type", "clear", "select", "check", "press", "scroll", "wait"]);
const TAB_OPERATIONS = new Set(["tabs", "open", "activate", "foreground", "close", "reload", "navigate", "back", "forward", "frames", "screenshot", "capabilities", "batch"]);
let connected = false, lastError = "", lastEndpoint = "";
let config = {}, generation = 0;
const activeRequests = new Set(), transportWaiters = new Set();
const results = [], tabJobs = new Map(), connectionRuntimes = new Map();
const MAX_OUTSTANDING = 32, MAX_EXECUTING = 4;
let outstanding = 0, executing = 0, barrier = Promise.resolve();
const executionWaiters = [];
function notifyTransport() { for (const resolve of transportWaiters) resolve(); transportWaiters.clear(); }
function waitForTransport() { return new Promise(resolve => transportWaiters.add(resolve)); }
function sessionCurrent(current) {
  if (!current.connectionId) return generation === current.generation;
  return connectionRuntimes.get(current.connectionId) === current.runtime && current.runtime.active;
}
function authorized(current) { return config.enabled === true && sessionCurrent(current); }
function finishOutstanding(current) {
  outstanding--;
  if (current.runtime) current.runtime.outstanding--;
}
function profilesFor(storage) {
  if (typeof normalizeBridgeConnections === "function") return normalizeBridgeConnections(storage);
  // Isolated legacy test harnesses load background.js alone; shipped builds
  // always load the shared validator before this file.
  if (storage.connections !== undefined) throw Error("Connection schema unavailable");
  return storage.url && storage.token && storage.device ? [{...storage, id: "legacy", name: "Collegamento esistente", enabled: true}] : [];
}
async function acquireExecution() {
  if (executing < MAX_EXECUTING) { executing++; return; }
  await new Promise(resolve => executionWaiters.push(resolve));
}
function releaseExecution() {
  const next = executionWaiters.shift();
  if (next) next(); else executing--;
}
function scheduleCommand(command, current) {
  // Commands on the same tab stay ordered. Commands changing the active tab,
  // batches and implicit-tab commands are barriers across all earlier work.
  const tabId = command.args?.tabId;
  const perTab = tabId != null && command.op !== "open" && command.op !== "activate" && command.op !== "foreground" && command.op !== "close" && command.op !== "batch";
  const key = String(tabId);
  const dependencies = perTab ? [barrier, tabJobs.get(key)] : [barrier, ...tabJobs.values()];
  outstanding++;
  if (current.runtime) current.runtime.outstanding++;
  const job = Promise.all(dependencies.filter(Boolean)).then(async () => {
    await acquireExecution();
    const started = performance.now();
    let completion;
    try {
      if (!authorized(current)) throw Error("Control disabled before execution");
      completion = {device: current.device, id: command.id, result: await execute(command)};
    } catch (error) {
      completion = {device: current.device, id: command.id, error: (error.code ? error.code + ": " : "") + error.message};
    } finally { releaseExecution(); }
    completion.durationMs = performance.now() - started;
    if (authorized(current)) (current.runtime?.results || results).push({payload: completion, current});
    else finishOutstanding(current);
    notifyTransport();
  });
  if (perTab) {
    tabJobs.set(key, job);
    job.then(() => { if (tabJobs.get(key) === job) tabJobs.delete(key); });
  } else { barrier = job; tabJobs.clear(); }
  return job;
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function checkURL(value) {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) throw Error("Only HTTP(S) page URLs allowed");
  return url.href;
}
function waitForTab(tabId, timeout = 10000, options = {}) {
  return new Promise((resolve, reject) => {
    let finished = false, observedNavigation = false;
    const timer = setTimeout(() => finish(Error("Navigation timed out")), timeout);
    function finish(error, tab) {
      if (finished) return;
      finished = true; clearTimeout(timer);
      browser.tabs.onUpdated.removeListener(updated); browser.tabs.onRemoved.removeListener(removed);
      browser.webNavigation?.onCommitted?.removeListener(committed);
      error ? reject(error) : resolve(tab);
    }
    function ready(tab) {
      // A newly-created Android tab can initially report about:blank/complete.
      // An existing tab can still report the previous document while its
      // navigation API promise resolves. Neither is the requested completion.
      if (!tab || tab.status !== "complete" || !/^https?:/i.test(tab.url || "")) return;
      if (options.action && !observedNavigation && tab.url === options.previousURL) return;
      finish(null, tab);
    }
    function updated(id, change, tab) {
      if (id !== tabId) return;
      if (change.status === "loading" || (change.url && change.url !== options.previousURL)) observedNavigation = true;
      if (change.status === "complete") ready(tab);
    }
    function committed(details) {
      if (details.tabId === tabId && details.frameId === 0) observedNavigation = true;
    }
    function removed(id) { if (id === tabId) finish(Error("Tab closed during navigation")); }
    browser.tabs.onUpdated.addListener(updated); browser.tabs.onRemoved.addListener(removed);
    browser.webNavigation?.onCommitted?.addListener(committed);
    // Listeners exist before invoking the navigation, including instant cached
    // loads and redirects. Creation is the exception: its tab ID arrives first.
    Promise.resolve().then(() => options.action?.()).then(() => browser.tabs.get(tabId)).then(ready).catch(error => finish(error));
  });
}
async function sendPage(tabId, op, args) {
  const requested = Number(args.timeoutMs ?? 5000);
  const limit = op === "wait" ? Math.min(15000, Math.max(0, Number.isFinite(requested) ? requested : 5000)) + 1500 : 10000;
  let timer;
  const deadline = {expired: false};
  try {
    // Android can suspend an inactive tab's message reply and its page timers.
    // The background deadline releases scheduling barriers without retrying an
    // action or claiming that its late completion has been canceled.
    return await Promise.race([sendPageMessage(tabId, op, args, deadline), new Promise((_, reject) => {
      timer = setTimeout(() => { deadline.expired = true; reject(Object.assign(Error("Page response timed out; an inactive Android tab may be suspended. Run foreground for this tab and open Firefox on Android. The action may still complete; do not repeat it automatically."), {code: "PAGE_RESPONSE_TIMEOUT"})); }, limit);
    })]);
  } finally { clearTimeout(timer); }
}
async function sendPageMessage(tabId, op, args, deadline) {
  const assertLive = () => {
    if (deadline.expired) throw Object.assign(Error("Page response deadline passed; the action was not retried."), {code: "PAGE_RESPONSE_TIMEOUT"});
  };
  const options = {frameId: args.frameId ?? 0}, message = {type: "browser-bridge.command", engineVersion: browser.runtime.getManifest().version, op, args};
  let response;
  try { assertLive(); response = await browser.tabs.sendMessage(tabId, message, options); }
  catch (error) {
    if (!/receiving end|establish connection|message port|No matching message handler/i.test(error.message)) throw error;
    // Existing tabs after an extension update may not yet have the resident engine.
    assertLive();
    await browser.tabs.executeScript(tabId, {file: "page.js", frameId: options.frameId, runAt: "document_start"});
    assertLive();
    response = await browser.tabs.sendMessage(tabId, message, options);
  }
  if (response?.error?.code === "ENGINE_VERSION_MISMATCH") {
    // The version handshake rejected the action before execution, so replacing
    // the fixed resident engine and sending it once is safe after an upgrade.
    assertLive();
    await browser.tabs.executeScript(tabId, {file: "page.js", frameId: options.frameId, runAt: "document_start"});
    assertLive();
    response = await browser.tabs.sendMessage(tabId, message, options);
  }
  if (response?.engineVersion && response.engineVersion !== message.engineVersion) throw Error("Page engine version mismatch; reload this tab");
  if (response?.error) throw Object.assign(Error(response.error.message), {code: response.error.code});
  if (!response || !("result" in response)) throw Error("Page engine did not return a result");
  return response.result;
}
async function execute(command) {
  const {op, args = {}} = command;
  if (!PAGE_OPERATIONS.has(op) && !TAB_OPERATIONS.has(op)) throw Error("Unsupported operation");
  if (op === "capabilities") return {version: browser.runtime.getManifest().version,
    operations: [...TAB_OPERATIONS, ...PAGE_OPERATIONS], transport: "HTTP long-poll", trustedEvents: false,
    frames: typeof browser.webNavigation?.getAllFrames === "function", screenshot: typeof browser.tabs.captureTab === "function",
    openShadowRoots: true, closedShadowRoots: false, nativeAndroidUI: false, foregroundAPI: {tabActivation: true, windowFocus: typeof browser.windows?.update === "function", androidOSForegroundGuaranteed: false}, parallelTabs: true, maxParallelCommands: MAX_EXECUTING};
  if (op === "batch") {
    if (!Array.isArray(args.steps) || args.steps.length < 1 || args.steps.length > 25 || args.steps.some(step => step.op === "batch")) throw Error("batch requires 1–25 non-nested steps");
    const results = [];
    for (let index = 0; index < args.steps.length; index++) {
      const step = args.steps[index];
      try { results.push({op: step.op, result: await execute({op: step.op, args: {...(args.tabId == null ? {} : {tabId: args.tabId}), ...step.args}})}); }
      catch (error) { return {results, completed: results.length, error: {index, code: error.code || "ACTION_ERROR", message: error.message}}; }
    }
    return {results, completed: results.length};
  }
  if (op === "tabs") return (await browser.tabs.query({})).map(tab => ({id: tab.id, title: tab.title, url: tab.url, active: tab.active, status: tab.status}));
  if (op === "open") {
    const tab = await browser.tabs.create({url: checkURL(args.url), active: args.active ?? true});
    if (args.waitUntil === "complete") await waitForTab(tab.id, args.timeoutMs);
    return {id: tab.id};
  }
  const tab = args.tabId != null ? await browser.tabs.get(Number(args.tabId)) : (await browser.tabs.query({active: true, currentWindow: true}))[0];
  if (!tab) throw Error("No active tab");
  if (op === "activate" || op === "foreground") {
    const activeTab = await browser.tabs.update(tab.id, {active: true});
    const windowId = activeTab?.windowId ?? tab.windowId;
    const windowFocusSupported = typeof browser.windows?.update === "function" && Number.isInteger(windowId);
    const result = {ok: true, tabId: tab.id, tabActivated: true, windowFocusSupported,
      windowFocusRequested: false, windowFocused: null, androidOSForegroundGuaranteed: false};
    if (windowFocusSupported) {
      try {
        const window = await browser.windows.update(windowId, {focused: true});
        result.windowFocusRequested = true; result.windowFocused = window?.focused ?? null;
      } catch (error) { result.windowFocusError = error.message; }
    }
    if (!result.windowFocusRequested) result.nextStep = "If Firefox remains in the background on Android, open Firefox on the device; extensions cannot guarantee Android app foregrounding.";
    return result;
  }
  if (op === "close") { await browser.tabs.remove(tab.id); return {ok: true}; }
  if (op === "navigate") {
    const action = () => browser.tabs.update(tab.id, {url: checkURL(args.url)});
    if (args.waitUntil === "complete") await waitForTab(tab.id, args.timeoutMs, {previousURL: tab.url, action});
    else await action();
    return {id: tab.id};
  }
  if (op === "reload" || op === "back" || op === "forward") {
    const action = () => op === "reload" ? browser.tabs.reload(tab.id) : op === "back" ? browser.tabs.goBack(tab.id) : browser.tabs.goForward(tab.id);
    if (args.waitUntil === "complete") await waitForTab(tab.id, args.timeoutMs, {previousURL: tab.url, action});
    else await action();
    return {ok: true};
  }
  checkURL(tab.url);
  if (op === "frames") return (await browser.webNavigation.getAllFrames({tabId: tab.id})).map(frame => ({frameId: frame.frameId, parentFrameId: frame.parentFrameId, url: frame.url}));
  if (op === "screenshot") {
    if (typeof browser.tabs.captureTab !== "function") throw Error("Screenshot API is unavailable in this browser");
    const format = args.format || "jpeg", quality = args.quality ?? 80;
    if (!["jpeg", "png"].includes(format) || quality < 1 || quality > 100) throw Error("Invalid screenshot format or quality");
    let dataURL;
    try { dataURL = await browser.tabs.captureTab(tab.id, {format, quality}); }
    catch (error) {
      if (/not visible|invisible|not active|background|not currently displayed|not selected/i.test(error.message)) {
        throw Object.assign(Error("Tab is not visible. Run foreground for this tab, then open Firefox on Android if it remains in the background, and retry screenshot."), {code: "TAB_NOT_VISIBLE"});
      }
      throw error;
    }
    const [, mimeType, data] = dataURL.match(/^data:([^;]+);base64,(.+)$/);
    return {mimeType, data, tabId: tab.id};
  }
  return await sendPage(tab.id, op, args);
}
async function request(current, path, data) {
  const runtime = current.runtime;
  const urls = [...new Set(current.urls || [current.url])];
  const preferred = runtime ? runtime.endpoint : lastEndpoint;
  if (urls.includes(preferred)) urls.sort((a, b) => Number(b === preferred) - Number(a === preferred));
  let failure;
  for (const endpoint of urls) {
    if (!sessionCurrent(current)) throw Error("Connection disabled or changed");
    const controller = new AbortController(); activeRequests.add(controller); runtime?.requests.add(controller);
    const timer = setTimeout(() => controller.abort(), (data.waitMs || 0) + 5000);
    try {
      const response = await fetch(validateBridgeOrigin(endpoint) + path, {
        method: "POST", headers: {Authorization: "Bearer " + current.token, "Content-Type": "application/json"},
        body: JSON.stringify(data), signal: controller.signal, cache: "no-store"
      });
      if (!response.ok) throw Error(`Bridge HTTP ${response.status}`);
      const reply = await response.json();
      if (!sessionCurrent(current)) throw Error("Connection disabled or changed");
      if (runtime) runtime.endpoint = endpoint; else lastEndpoint = endpoint;
      return reply;
    } catch (error) { failure = error; if (!sessionCurrent(current)) throw error; }
    finally { clearTimeout(timer); activeRequests.delete(controller); runtime?.requests.delete(controller); }
  }
  throw failure || Error("No reachable broker");
}
async function sendResults(runtime) {
  const queue = runtime.results;
  let backoff = 250;
  while (runtime.active) {
    if (!queue.length) { await waitForTransport(); continue; }
    const entry = queue[0];
    if (!authorized(entry.current)) {
      queue.shift(); finishOutstanding(entry.current); notifyTransport(); continue;
    }
    try {
      // Each broker has its own reporter. An unreachable service never blocks
      // completion reports for other services, and actions are never retried.
      await request(entry.current, "/api/result", entry.payload);
      if (queue[0] === entry) { queue.shift(); finishOutstanding(entry.current); }
      backoff = 250; notifyTransport();
    } catch (error) {
      if (authorized(entry.current)) {
        runtime.error = error.message; await delay(backoff); backoff = Math.min(5000, backoff * 2);
      }
    }
  }
}
async function pollConnection(runtime) {
  let backoff = 250, firstPoll = true;
  const current = {...runtime.profile, connectionId: runtime.profile.id, runtime};
  while (runtime.active) {
    if (runtime.outstanding >= MAX_OUTSTANDING) { await waitForTransport(); continue; }
    try {
      const reply = await request(current, "/api/poll", {device: current.device, version: browser.runtime.getManifest().version, waitMs: firstPoll ? 0 : 20000});
      if (!authorized(current)) break;
      firstPoll = false; runtime.connected = true; runtime.error = ""; backoff = 250;
      if (reply.command) scheduleCommand(reply.command, current);
    } catch (error) {
      runtime.connected = false;
      if (runtime.active) { runtime.error = error.message; await delay(backoff); backoff = Math.min(5000, backoff * 2); }
      firstPoll = true;
    }
  }
}
function stopConnection(runtime) {
  runtime.active = false; runtime.connected = false;
  for (const controller of runtime.requests) controller.abort();
  // Already executing actions cannot be undone. Their late results are
  // discarded and never sent to a replacement connection or credential.
  for (const entry of runtime.results) finishOutstanding(entry.current);
  runtime.results.length = 0;
  notifyTransport();
}
function syncConnections() {
  let profiles;
  try { profiles = profilesFor(config); lastError = ""; }
  catch (error) { profiles = []; lastError = error.message; }
  const selected = new Map(profiles.filter(profile => config.enabled === true && profile.enabled).map(profile => [profile.id, profile]));
  for (const [id, runtime] of connectionRuntimes) {
    const profile = selected.get(id);
    const fingerprint = profile ? JSON.stringify({url: profile.url, urls: profile.urls, token: profile.token, device: profile.device}) : null;
    if (!profile || fingerprint !== runtime.fingerprint) { stopConnection(runtime); connectionRuntimes.delete(id); }
    else runtime.profile = profile;
  }
  for (const [id, profile] of selected) {
    if (connectionRuntimes.has(id)) continue;
    const runtime = {profile, fingerprint: JSON.stringify({url: profile.url, urls: profile.urls, token: profile.token, device: profile.device}), active: true,
      connected: false, error: "", endpoint: "", requests: new Set(), results: [], outstanding: 0};
    connectionRuntimes.set(id, runtime);
    sendResults(runtime); pollConnection(runtime);
  }
  connected = [...connectionRuntimes.values()].some(runtime => runtime.connected);
  notifyTransport();
}
async function loop() {
  const initialGeneration = generation;
  const initial = await browser.storage.local.get(["connections", "url", "urls", "token", "device", "enabled"]);
  // Preserve a storage change occurring while the initial read was pending.
  if (initialGeneration === generation) config = initial;
  else config = {...initial, ...config};
  syncConnections();
}
browser.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  const keys = ["connections", "url", "urls", "token", "device", "enabled"];
  if (!keys.some(key => key in changes)) return;
  for (const key of keys) if (key in changes) config[key] = changes[key].newValue;
  generation++;
  // Legacy scheduler clients are invalidated globally. Real connection workers
  // retain their own identity and only changed/removed profiles are aborted.
  for (const controller of activeRequests) {
    if (![...connectionRuntimes.values()].some(runtime => runtime.requests.has(controller))) controller.abort();
  }
  syncConnections();
});
browser.runtime.onMessage.addListener(message => {
  if (message.type !== "status") return undefined;
  let profiles = [];
  try { profiles = profilesFor(config); } catch (_) {}
  const statuses = profiles.map(profile => {
    const runtime = connectionRuntimes.get(profile.id);
    return typeof bridgeConnectionStatus === "function" ? bridgeConnectionStatus(profile, runtime) :
      {id: profile.id, name: profile.name, url: profile.url, device: profile.device, enabled: profile.enabled, connected: !!runtime?.connected, error: runtime?.error || "", endpoint: runtime?.endpoint || ""};
  });
  const online = statuses.find(status => status.connected);
  return Promise.resolve({connected: !!online, error: lastError || statuses.find(status => status.error)?.error || "", endpoint: online?.endpoint || "", enabled: config.enabled === true, connections: statuses});
});
browser.browserAction.onClicked.addListener(() => browser.runtime.openOptionsPage());
browser.runtime.onInstalled.addListener(details => { if (details.reason === "install") browser.runtime.openOptionsPage(); });
loop();
