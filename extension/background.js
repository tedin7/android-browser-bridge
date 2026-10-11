/* Fixed, user-authorized operations only; no server-supplied script execution. */
let lastError = "", connected = false, lastEndpoint = "";
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function pageOperation(command) {
  const {op, args = {}} = command;
  function selectorFor(element) {
    const parts = [];
    for (let el = element; el && el.nodeType === 1; el = el.parentElement) {
      if (el.id && document.querySelectorAll("#" + CSS.escape(el.id)).length === 1) {
        parts.unshift("#" + CSS.escape(el.id)); break;
      }
      const siblings = el.parentElement ? [...el.parentElement.children].filter(sibling => sibling.tagName === el.tagName) : [el];
      parts.unshift(el.tagName.toLowerCase() + (siblings.length > 1 ? `:nth-of-type(${siblings.indexOf(el) + 1})` : ""));
    }
    return parts.join(" > ");
  }
  if (op === "read") return {url: location.href, title: document.title,
    text: document.body?.innerText.slice(0, 60000) || "",
    elements: [...document.querySelectorAll("a,button,input,textarea,select,[role=button]")]
      .slice(0, 300).map(el => ({selector: selectorFor(el), tag: el.tagName, id: el.id, name: el.getAttribute("name"),
        text: (el.innerText || el.getAttribute("aria-label") || "").slice(0, 150),
        type: el.getAttribute("type"), href: el.getAttribute("href")}))};
  if (op === "scroll") { window.scrollBy(Number(args.x || 0), Number(args.y || 500)); return {ok: true}; }
  if (!args.selector || typeof args.selector !== "string") throw Error("selector required");
  const matches = document.querySelectorAll(args.selector);
  if (matches.length !== 1) throw Error(`Selector must match one element; matched ${matches.length}`);
  const el = matches[0];
  if (op === "click") { el.scrollIntoView({block: "center"}); el.click(); return {ok: true}; }
  if (op === "fill") {
    if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) throw Error("Use an input or textarea");
    const proto = el instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    el.focus(); setter.call(el, String(args.value ?? ""));
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true})); return {ok: true};
  }
  throw Error("Unsupported page operation");
}
async function execute(command) {
  const {op, args = {}} = command;
  if (op === "tabs") return (await browser.tabs.query({})).map(t => ({id: t.id, title: t.title, url: t.url, active: t.active}));
  if (op === "open") {
    const url = new URL(args.url);
    if (!["https:", "http:"].includes(url.protocol)) throw Error("Only HTTP(S) URLs allowed");
    const tab = await browser.tabs.create({url: url.href}); return {id: tab.id};
  }
  const tab = args.tabId != null ? await browser.tabs.get(Number(args.tabId)) :
    (await browser.tabs.query({active: true, currentWindow: true}))[0];
  if (!tab) throw Error("No active tab");
  if (op === "activate") { await browser.tabs.update(tab.id, {active: true}); return {ok: true}; }
  if (op === "close") { await browser.tabs.remove(tab.id); return {ok: true}; }
  if (op === "reload") { await browser.tabs.reload(tab.id); return {ok: true}; }
  if (!["read", "click", "fill", "scroll"].includes(op)) throw Error("Unsupported operation");
  const code = `(${pageOperation.toString()})(${JSON.stringify(command)})`;
  return (await browser.tabs.executeScript(tab.id, {code}))[0];
}
async function request(config, path, data) {
  const urls = [...new Set(config.urls || [config.url])];
  if (urls.includes(lastEndpoint)) urls.sort((a, b) => Number(b === lastEndpoint) - Number(a === lastEndpoint));
  let failure;
  for (const endpoint of urls) {
    try {
      const origin = validateBridgeOrigin(endpoint);
      const response = await fetch(origin + path, {
    method: "POST", headers: {"Authorization": "Bearer " + config.token, "Content-Type": "application/json"},
    body: JSON.stringify(data), signal: AbortSignal.timeout(5000)
  });
      if (!response.ok) throw Error(`Bridge HTTP ${response.status}`);
      const reply = await response.json(); lastEndpoint = endpoint; return reply;
    } catch (error) { failure = error; }
  }
  throw failure || Error("Nessun indirizzo raggiungibile");
}
async function loop() {
  let pending = null;
  for (;;) {
    const config = await browser.storage.local.get(["url", "urls", "token", "device", "enabled"]);
    connected = false;
    if (config.enabled && config.url && config.token && config.device) {
      try {
        if (pending && (pending.session.url !== config.url || pending.session.token !== config.token || pending.session.device !== config.device)) pending = null;
        if (pending) {
          await request(config, "/api/result", pending); pending = null;
        }
        const reply = await request(config, "/api/poll", {device: config.device});
        connected = true; lastError = "";
        if (reply.command) {
          const command = reply.command;
          try { pending = {device: config.device, id: command.id, result: await execute(command)}; }
          catch (error) { pending = {device: config.device, id: command.id, error: String(error.message || error)}; }
          Object.defineProperty(pending, "session", {value: {url: config.url, token: config.token, device: config.device}});
          await request(config, "/api/result", pending); pending = null;
        }
      } catch (error) { lastError = String(error.message || error); }
    }
    await delay(1000);
  }
}
browser.runtime.onMessage.addListener(message => {
  if (message.type === "status") return Promise.resolve({connected, error: lastError});
});
browser.browserAction.onClicked.addListener(() => browser.runtime.openOptionsPage());
browser.runtime.onInstalled.addListener(details => {
  if (details.reason === "install") browser.runtime.openOptionsPage();
});
loop();
