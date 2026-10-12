#!/usr/bin/env node
/* Optional desktop diagnostics. No arbitrary JS, page writes, cookies or bodies. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const METHODS = new Set(['Runtime.enable', 'Runtime.disable', 'Log.enable', 'Log.disable', 'Network.enable', 'Network.disable', 'Performance.enable', 'Performance.disable', 'Performance.getMetrics']);
const MAX_EVENTS = 100;

export function localEndpoint(raw) {
  const url = new URL(raw);
  if (url.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || !url.port || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw Error('Explicit loopback HTTP debugger endpoint with port required');
  return url;
}

export function options(argv) {
  const result = {durationMs: 1000};
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i], value = argv[i + 1];
    if (value === undefined || !['--endpoint', '--tab-url', '--duration-ms', '--output'].includes(flag)) throw Error('Unknown or missing argument');
    const name = {'--endpoint': 'endpoint', '--tab-url': 'tabUrl', '--duration-ms': 'durationMs', '--output': 'output'}[flag];
    if (Object.hasOwn(result, name) && name !== 'durationMs') throw Error('Duplicate argument');
    result[name] = name === 'durationMs' ? Number(value) : value;
  }
  localEndpoint(result.endpoint);
  const tab = new URL(result.tabUrl);
  if (!['http:', 'https:'].includes(tab.protocol) || tab.username || tab.password) throw Error('Exact HTTP(S) target URL required');
  if (!result.output || !Number.isInteger(result.durationMs) || result.durationMs < 1 || result.durationMs > 10000) throw Error('Output path and duration 1..10000 ms required');
  return result;
}

export function targetSocket(endpoint, targets, exactUrl) {
  if (!Array.isArray(targets)) throw Error('Invalid target list');
  const matches = targets.filter(item => item.type === 'page' && item.url === exactUrl);
  if (matches.length !== 1) throw Error('Expected exactly one matching page target');
  const target = matches[0], socket = new URL(target.webSocketDebuggerUrl);
  const origin = localEndpoint(endpoint);
  if (socket.protocol !== 'ws:' || socket.hostname !== origin.hostname || socket.port !== origin.port || socket.username || socket.password || socket.search || socket.hash || !socket.pathname.startsWith('/devtools/page/')) throw Error('Debugger target must remain on the explicit loopback endpoint');
  return socket.href;
}

const bounded = (value, limit = 512) => typeof value === 'string' ? value.slice(0, limit) : '';
export function recordEvent(report, message) {
  const p = message.params || {};
  const push = (name, value) => {
    if (report[name].length < MAX_EVENTS) report[name].push(value);
    else report.omittedEvents++;
  };
  if (message.method === 'Runtime.consoleAPICalled') {
    push('console', {type: bounded(p.type, 40), timestamp: p.timestamp,
      values: (p.args || []).slice(0, 10).map(arg => ({type: bounded(arg.type, 40), value: typeof arg.value === 'string' ? bounded(arg.value) : ['number', 'boolean'].includes(typeof arg.value) ? arg.value : undefined, description: bounded(arg.description)}))});
  } else if (message.method === 'Log.entryAdded') {
    const e = p.entry || {};
    push('console', {source: bounded(e.source, 40), level: bounded(e.level, 40), text: bounded(e.text), timestamp: e.timestamp});
  } else if (message.method === 'Network.requestWillBeSent') {
    push('network', {kind: 'request', requestId: bounded(p.requestId, 100), url: bounded(p.request?.url, 2048), method: bounded(p.request?.method, 16), timestamp: p.timestamp});
  } else if (message.method === 'Network.responseReceived') {
    push('network', {kind: 'response', requestId: bounded(p.requestId, 100), status: p.response?.status, mimeType: bounded(p.response?.mimeType, 100), timestamp: p.timestamp});
  } else if (message.method === 'Network.loadingFailed') {
    push('network', {kind: 'failed', requestId: bounded(p.requestId, 100), errorText: bounded(p.errorText), canceled: p.canceled === true});
  }
}

export class FixedCDP {
  constructor(socket, onEvent) {
    this.socket = socket;
    this.onEvent = onEvent;
    this.nextId = 1;
    this.pending = new Map();
    socket.addEventListener('message', event => {
      if (typeof event.data !== 'string' || event.data.length > 2 * 1024 * 1024) return;
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id); clearTimeout(pending.timer);
        if (message.error) pending.reject(Error('CDP request rejected'));
        else pending.resolve(message.result || {});
      } else if (typeof message.method === 'string') this.onEvent(message);
    });
    const closed = () => {
      for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(Error('CDP disconnected')); }
      this.pending.clear();
    };
    socket.addEventListener('close', closed);
    socket.addEventListener('error', closed);
  }
  call(method) {
    if (!METHODS.has(method)) return Promise.reject(Error('Unsupported diagnostic method'));
    return new Promise((resolve, reject) => {
      const id = this.nextId++;
      const timer = setTimeout(() => { this.pending.delete(id); reject(Error('CDP request timed out')); }, 3000);
      this.pending.set(id, {resolve, reject, timer});
      try { this.socket.send(JSON.stringify({id, method, params: {}})); }
      catch { clearTimeout(timer); this.pending.delete(id); reject(Error('CDP send failed')); }
    });
  }
}

export async function collect(config, dependencies = {}) {
  const endpoint = localEndpoint(config.endpoint);
  const request = dependencies.fetch || globalThis.fetch;
  const response = await request(new URL('/json/list', endpoint), {redirect: 'error', signal: AbortSignal.timeout(3000)});
  if (!response.ok) throw Error('Debugger discovery failed');
  // Streaming bound avoids accepting an unbounded discovery response.
  const reader = response.body.getReader();
  const parts = []; let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 1024 * 1024) throw Error('Debugger discovery exceeds limit');
      parts.push(Buffer.from(value));
    }
  } finally { await reader.cancel(); }
  const socketUrl = targetSocket(endpoint.href, JSON.parse(Buffer.concat(parts).toString()), config.tabUrl);
  const Socket = dependencies.WebSocket || globalThis.WebSocket;
  if (typeof Socket !== 'function') throw Error('Node built-in WebSocket unavailable');
  const socket = new Socket(socketUrl);
  const report = {backend: 'chrome-cdp', platform: 'desktop', version: 1, console: [], network: [], metrics: [], omittedEvents: 0};
  const enabled = [];
  const cdp = new FixedCDP(socket, event => recordEvent(report, event));
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Debugger connection timed out')), 3000);
      socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, {once: true});
      socket.addEventListener('error', () => { clearTimeout(timer); reject(Error('Debugger connection failed')); }, {once: true});
    });
    for (const domain of ['Runtime', 'Log', 'Network', 'Performance']) { await cdp.call(domain+'.enable'); enabled.push(domain); }
    await new Promise(resolve => setTimeout(resolve, config.durationMs));
    const metrics = await cdp.call('Performance.getMetrics');
    report.metrics = (metrics.metrics || []).filter(item => typeof item.name === 'string' && Number.isFinite(item.value)).slice(0, 256).map(item => ({name: bounded(item.name, 100), value: item.value}));
  } finally {
    for (const domain of enabled.reverse()) {
      if (socket.readyState === 1) { try { await cdp.call(domain+'.disable'); } catch {} }
    }
    socket.close();
  }
  await fs.mkdir(path.dirname(path.resolve(config.output)), {recursive: true, mode: 0o700});
  const file = await fs.open(config.output, 'wx', 0o600);
  try { await file.writeFile(JSON.stringify(report)); await file.sync(); }
  finally { await file.close(); }
  return {backend: report.backend, platform: 'desktop', artifact: path.resolve(config.output),
    consoleEvents: report.console.length, networkEvents: report.network.length, metrics: report.metrics.length, omittedEvents: report.omittedEvents};
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try { console.log(JSON.stringify(await collect(options(process.argv.slice(2))))); }
  catch { console.log(JSON.stringify({error: 'DESKTOP_DIAGNOSTICS_FAILED', nextSteps: ['Use an explicitly started local debugging browser, one exact existing page URL and a new private output path.']})); process.exitCode = 1; }
}
