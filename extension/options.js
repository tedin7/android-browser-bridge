const fields = ["url", "urls", "token", "device", "enabled"];
browser.storage.local.get(fields).then(config => {
  for (const key of fields) if (config[key] !== undefined) {
    const el = document.getElementById(key);
    if (!el) continue;
    if (key === "device") { el.textContent = "Dispositivo: " + config[key]; continue; }
    if (key === "enabled") el.checked = config[key]; else el.value = config[key];
  }
});
document.getElementById("config").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    let code = document.getElementById("code").value.trim();
    let origin = document.getElementById("url").value;
    let alternatives = [];
    if (code.startsWith("BB1.")) {
      const encoded = code.slice(4).replace(/-/g, "+").replace(/_/g, "/");
      const bundle = JSON.parse(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "=")));
      origin = bundle.url; code = bundle.code;
      alternatives = bundle.urls || [];
    }
    const url = validateBridgeOrigin(origin);
    if (!Array.isArray(alternatives) || alternatives.length > 4) throw Error("Indirizzi alternativi non validi");
    const urls = [...new Set([url, ...alternatives.map(validateBridgeOrigin)])];
    const previous = await browser.storage.local.get(fields);
    const config = {url, urls, enabled: document.getElementById("enabled").checked};
    if (code) {
      let response;
      for (const endpoint of urls) {
        try { response = await fetch(endpoint + "/api/pair", {method: "POST",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify({code: code.toUpperCase()}), signal: AbortSignal.timeout(15000)});
          if (response.ok || response.status < 500) break;
        } catch (error) { if (endpoint === urls[urls.length - 1]) throw error; }
      }
      if (!response) throw Error("Nessun indirizzo raggiungibile");
      const result = await response.json();
      if (!response.ok) throw Error(result.error || "Abbinamento fallito");
      config.token = result.token; config.device = result.device;
    } else if (!previous.token || previous.url !== config.url) {
      throw Error("Inserisci un codice di abbinamento valido per questo servizio.");
    } else {
      config.urls = previous.urls || urls;
    }
    await browser.storage.local.set(config);
    document.getElementById("url").value = config.url;
    document.getElementById("code").value = "";
    document.getElementById("device").textContent = "Dispositivo: " + (config.device || previous.device);
    document.getElementById("status").textContent = "Salvato.";
  } catch (error) { document.getElementById("status").textContent = error.message; }
});
setInterval(async () => {
  const status = await browser.runtime.sendMessage({type: "status"});
  document.getElementById("status").textContent = status.connected ? "Collegato" : (status.error || "In attesa / disabilitato");
}, 2000);
