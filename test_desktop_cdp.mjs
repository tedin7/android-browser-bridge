import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {FixedCDP, options, targetSocket, recordEvent, collect} from './desktop_cdp.mjs';

for (const endpoint of ['https://127.0.0.1:9222', 'http://public.example:9222', 'http://u:p@localhost:9222', 'http://localhost:9222/other']) {
  assert.throws(() => options(['--endpoint', endpoint, '--tab-url', 'https://example.org/', '--output', '/tmp/result']));
}
const endpoint = 'http://127.0.0.1:9222/';
const target = {type: 'page', url: 'https://example.org/', webSocketDebuggerUrl: 'ws://127.0.0.1:9222/devtools/page/fixture'};
assert.equal(targetSocket(endpoint, [target], target.url), target.webSocketDebuggerUrl);
assert.throws(() => targetSocket(endpoint, [target, target], target.url));
assert.throws(() => targetSocket(endpoint, [{...target, webSocketDebuggerUrl: 'ws://remote.example:9222/devtools/page/fixture'}], target.url));

class FakeSocket extends EventTarget {
  constructor() { super(); this.readyState = 1; this.sent = []; queueMicrotask(() => this.dispatchEvent(new Event('open'))); }
  send(raw) {
    const request = JSON.parse(raw); this.sent.push(request);
    const result = request.method === 'Performance.getMetrics' ? {metrics: [{name: 'TaskDuration', value: 2}, {name: 'bad', value: 'text'}]} : {};
    queueMicrotask(() => {
      this.dispatchEvent(new MessageEvent('message', {data: JSON.stringify({id: request.id, result})}));
      if (request.method === 'Log.enable') this.dispatchEvent(new MessageEvent('message', {data: JSON.stringify({method: 'Log.entryAdded', params: {entry: {text: 'fixture console', level: 'info'}}})}));
    });
  }
  close() { this.readyState = 3; this.dispatchEvent(new Event('close')); }
}
const socket = new FakeSocket(), cdp = new FixedCDP(socket, () => {});
await assert.rejects(cdp.call('Runtime.evaluate'));
assert.equal(socket.sent.length, 0);
await cdp.call('Performance.getMetrics');
assert.deepEqual(socket.sent[0].params, {});
socket.close();
const report = {console: [], network: [], omittedEvents: 0};
for (let i = 0; i < 110; i++) recordEvent(report, {method: 'Network.requestWillBeSent', params: {request: {url: 'https://fixture/', headers: {Authorization: 'private'}, postData: 'secret'}}});
assert.equal(report.network.length, 100);
assert.equal(report.omittedEvents, 10);
assert(!JSON.stringify(report).includes('secret'));
assert(!JSON.stringify(report).includes('Authorization'));
const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'cdp-protocol-test-'));
try {
  const file = path.join(directory, 'audit.json');
  const summary = await collect({endpoint, tabUrl: target.url, output: file, durationMs: 1}, {
    WebSocket: FakeSocket,
    fetch: async () => new Response(JSON.stringify([target]), {status: 200})
  });
  assert.equal(summary.consoleEvents, 1);
  assert.equal(summary.metrics, 1);
  assert(!JSON.stringify(summary).includes('fixture console'));
  assert.equal((await fs.stat(file)).mode & 0o777, 0o600);
  assert.equal(JSON.parse(await fs.readFile(file, 'utf8')).metrics[0].name, 'TaskDuration');
} finally { await fs.rm(directory, {recursive: true, force: true}); }
console.log('Desktop CDP fixed-protocol and private-artifact tests passed');
