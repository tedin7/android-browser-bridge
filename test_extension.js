const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const tab = {id: 7, title: "Test", url: "https://example.org", active: true};
let injected = "";
const context = vm.createContext({URL, setTimeout, console,
  browser: {tabs: {
    query: async () => [tab], get: async id => ({...tab, id}),
    create: async args => { assert.equal(args.url, "https://example.org/"); return tab; },
    executeScript: async (id, args) => { assert.equal(id, 7); injected = args.code; return [{title: "Page"}]; }
  }, runtime: {onMessage: {addListener() {}}, onInstalled: {addListener() {}}},
  browserAction: {onClicked: {addListener() {}}}}
});
vm.runInContext(fs.readFileSync("extension/background.js", "utf8").replace(/loop\(\);\s*$/, ""), context);
vm.runInContext(fs.readFileSync("extension/connection.js", "utf8"), context);
(async () => {
  assert.equal((await context.execute({op: "tabs"}))[0].id, 7);
  assert.equal((await context.execute({op: "open", args: {url: "https://example.org"}})).id, 7);
  await assert.rejects(context.execute({op: "open", args: {url: "javascript:alert(1)"}}), /HTTP/);
  await assert.rejects(context.execute({op: "eval"}), /Unsupported/);
  assert.equal((await context.execute({op: "read"})).title, "Page");
  const command = {op: "fill", args: {selector: "input[name='x']", value: "quotes '\" and \\ literal"}};
  await context.execute(command);
  assert.ok(injected.includes(JSON.stringify(command)));
  let clicked = 0;
  const element = {scrollIntoView() {}, click() {clicked++;}};
  const page = vm.createContext({document: {querySelectorAll: () => [element]}});
  const operation = context.pageOperation.toString();
  assert.equal(vm.runInContext(`(${operation})({op:'click',args:{selector:'button'}})`, page).ok, true);
  assert.equal(clicked, 1);
  assert.equal(context.validateBridgeOrigin("http://192.168.1.10:8766"), "http://192.168.1.10:8766");
  assert.equal(context.validateBridgeOrigin("https://linux.example:8766"), "https://linux.example:8766");
  assert.throws(() => context.validateBridgeOrigin("http://8.8.8.8"), /HTTPS/);
  page.document.querySelectorAll = () => [element, element];
  assert.throws(() => vm.runInContext(`(${operation})({op:'click',args:{selector:'button'}})`, page), /match one/);
  let attempted = [];
  context.fetch = async url => { attempted.push(url); if (url.includes("192.168")) throw Error("offline LAN"); return {ok: true, json: async () => ({command: null})}; };
  context.AbortSignal = AbortSignal;
  const failover = await context.request({url: "http://192.168.1.10:8766", urls: ["http://192.168.1.10:8766", "https://linux.example:8766"], token: "test"}, "/api/poll", {});
  assert.equal(failover.command, null);
  assert.equal(attempted.length, 2);
  console.log("Extension operations passed (mock WebExtension API; Android runtime not tested).");
})().catch(error => {console.error(error); process.exitCode = 1;});
