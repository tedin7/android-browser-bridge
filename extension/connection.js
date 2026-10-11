function validateBridgeOrigin(origin) {
  const url = new URL(origin);
  const pieces = url.hostname.split(".").map(Number);
  const ipv4 = pieces.length === 4 && pieces.every(n => Number.isInteger(n) && n >= 0 && n <= 255);
  const privateIPv4 = ipv4 && (pieces[0] === 127 || pieces[0] === 10 ||
    (pieces[0] === 172 && pieces[1] >= 16 && pieces[1] <= 31) ||
    (pieces[0] === 192 && pieces[1] === 168) || (pieces[0] === 100 && pieces[1] >= 64 && pieces[1] <= 127));
  const privateIPv6 = url.hostname === "[::1]" || /^\[f[cd][0-9a-f]{2}:/i.test(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && (privateIPv4 || privateIPv6 || url.hostname === "localhost")))
    throw Error("Usa HTTPS su Internet; HTTP è consentito solo su una rete privata fidata.");
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/") throw Error("Indirizzo servizio non valido");
  return url.href.replace(/\/$/, "");
}
