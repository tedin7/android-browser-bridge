const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const tab = {id: 7, title: "Test", url: "https://example.org", active: true, status: "complete"};
let lastMessage, lastOptions, injection, receiverMissing = false;
const context = vm.createContext({URL, setTimeout, clearTimeout, AbortController, performance, console,
  browser: {tabs: {
    query: async () => [tab], get: async id => ({...tab, id}), create: async args => {assert.ok(args.url.startsWith("https://"));return tab;},
    sendMessage: async (id, message, options) => {assert.equal(id,7);if(receiverMissing){receiverMissing=false;throw Error("Receiving end does not exist");}lastMessage=message;lastOptions=options;return {result:{title:"Page"}};},
    executeScript: async (id,args) => {assert.equal(id,7);assert.equal(args.file,"page.js");assert.equal(args.code,undefined);injection=args;},
    onUpdated: {addListener() {},removeListener() {}}, onRemoved: {addListener() {},removeListener() {}},
    captureTab: async () => "data:image/jpeg;base64,dGVzdA=="
  }, storage:{onChanged:{addListener() {}}}, runtime: {getManifest:()=>({version:"0.2.0"}),onMessage:{addListener(){}},onInstalled:{addListener(){}}},
  webNavigation:{getAllFrames:async()=>[{frameId:0,parentFrameId:-1,url:tab.url}]}, browserAction:{onClicked:{addListener(){}}}}
});
vm.runInContext(fs.readFileSync("extension/connection.js","utf8"),context);
vm.runInContext(fs.readFileSync("extension/background.js","utf8").replace(/loop\(\);\s*$/,""),context);
(async()=>{
  assert.equal((await context.execute({op:"tabs"}))[0].id,7);
  assert.equal((await context.execute({op:"open",args:{url:"https://example.org",waitUntil:"complete"}})).id,7);
  await assert.rejects(context.execute({op:"open",args:{url:"javascript:alert(1)"}}),/HTTP/);
  await assert.rejects(context.execute({op:"eval"}),/Unsupported/);
  const args={selector:"input[name='x']",value:"quotes '\" and \\ literal",frameId:9};
  await context.execute({op:"fill",args});
  assert.equal(lastMessage.args.value,args.value);assert.equal(lastOptions.frameId,9);
  receiverMissing=true;assert.equal((await context.execute({op:"read"})).title,"Page");
  assert.equal(injection.file,"page.js");
  const batch=await context.execute({op:"batch",args:{steps:[{op:"read"},{op:"eval"},{op:"read"}]}});
  assert.equal(batch.completed,1);assert.equal(batch.error.index,1);
  assert.equal((await context.execute({op:"screenshot"})).mimeType,"image/jpeg");
  assert.equal((await context.execute({op:"frames"}))[0].frameId,0);
  assert.equal((await context.execute({op:"capabilities"})).trustedEvents,false);
  assert.equal(context.validateBridgeOrigin("http://192.168.1.10:8766"),"http://192.168.1.10:8766");
  assert.throws(()=>context.validateBridgeOrigin("http://8.8.8.8"),/HTTPS/);
  let attempted=[];
  context.fetch=async url=>{attempted.push(url);if(url.includes("192.168"))throw Error("offline LAN");return {ok:true,json:async()=>({command:null})};};
  const response=await context.request({url:"http://192.168.1.10:8766",urls:["http://192.168.1.10:8766","https://linux.example:8766"],token:"test",generation:0},"/api/poll",{});
  assert.equal(response.command,null);assert.equal(attempted.length,2);
  console.log("PASS: fixed-operation dispatch, static engine injection, frame targeting, batch failure boundary, screenshot, capabilities and network failover.");
  await navigationChecks();
  await schedulerChecks();
  await transportChecks();
})().catch(error=>{console.error(error);process.exitCode=1;});

async function runRegression(script) {
  const {spawnSync}=require('node:child_process');
  const result=spawnSync(process.execPath,['-e',script],{encoding:'utf8',timeout:5000});
  assert.equal(result.status,0,result.stderr || result.error?.message);
  process.stdout.write(result.stdout);
}
async function schedulerChecks() {await runRegression(SCHEDULER);}
async function transportChecks() {await runRegression(TRANSPORT);}
const SCHEDULER=String.raw`
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let storageChange;
const ctx=vm.createContext({URL,AbortController,setTimeout,clearTimeout,performance,console,browser:{storage:{onChanged:{addListener(fn){storageChange=fn;}}},runtime:{onMessage:{addListener(){}},onInstalled:{addListener(){}}},browserAction:{onClicked:{addListener(){}}}}});
vm.runInContext(fs.readFileSync('extension/background.js','utf8').replace(/loop\(\);\s*$/,''),ctx);
vm.runInContext('config={enabled:true}; generation=0;',ctx);
let started=[],running=0,peak=0,resolvers=new Map();
ctx.execute=async c=>{started.push(c.id);running++;peak=Math.max(peak,running);await new Promise(r=>resolvers.set(c.id,r));running--;return {ok:true};};
const session={generation:0,device:'test'};
const tick=()=>new Promise(r=>setTimeout(r,0));
const schedule=(id,tabId,op='read')=>ctx.scheduleCommand({id,op,args:tabId==null?{}:{tabId}},session);
(async()=>{
 const a=schedule('a',1),b=schedule('b',1),c=schedule('c',2); await tick();
 assert.deepEqual(started,['a','c']);resolvers.get('c')();await c;assert(!started.includes('b'));
 resolvers.get('a')();await a;await tick();assert(started.includes('b'));
 const global=schedule('global',undefined,'open'),later=schedule('later',3);await tick();assert(!started.includes('global'));
 resolvers.get('b')();await b;await tick();assert(started.includes('global'));assert(!started.includes('later'));
 resolvers.get('global')();await global;await tick();assert(started.includes('later'));resolvers.get('later')();await later;
 const jobs=[];for(let i=0;i<8;i++)jobs.push(schedule('limit'+i,100+i));await tick();assert.equal(running,4);
 for(let i=0;i<8;i++){while(!resolvers.has('limit'+i))await tick();resolvers.get('limit'+i)();await jobs[i];}assert.equal(peak,4);
 const active=schedule('active',200),cancelled=schedule('cancelled',200);await tick();storageChange({enabled:{newValue:false}},'local');resolvers.get('active')();await Promise.all([active,cancelled]);assert(!started.includes('cancelled'));
 console.log('PASS: parallel tabs, same-tab FIFO, global barriers, four-command bound and disable cancels queued actions.');
})().catch(e=>{console.error(e);process.exitCode=1;});
`;
const TRANSPORT=String.raw`
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let change, polls=0, reports=0, secondPollWaiting=false, resolveReport;
const reported=new Promise(r=>resolveReport=r);
const ctx=vm.createContext({URL,AbortController,setTimeout,clearTimeout,performance,console,fetch:async(url,options)=>{
 if(url.endsWith('/api/result')){reports++;assert(secondPollWaiting);resolveReport();return {ok:true,json:async()=>({ok:true})};}
 polls++;if(polls===1)return {ok:true,json:async()=>({command:{id:'one',op:'read',args:{tabId:1}}})};
 secondPollWaiting=true;return new Promise((r,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted'))));
},browser:{storage:{local:{get:async()=>({url:'http://127.0.0.1:8766',token:'test',device:'test',enabled:true})},onChanged:{addListener(f){change=f;}}},runtime:{getManifest:()=>({version:'0.2.0'}),onMessage:{addListener(){}},onInstalled:{addListener(){}}},browserAction:{onClicked:{addListener(){}}}}});
vm.runInContext(fs.readFileSync('extension/connection.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('extension/background.js','utf8').replace(/loop\(\);\s*$/,''),ctx);
ctx.execute=async()=>({ok:true});ctx.loop();
(async()=>{await Promise.race([reported,new Promise((_,reject)=>setTimeout(()=>reject(Error('report blocked by poll')),1000))]);change({enabled:{newValue:false}},'local');assert.equal(reports,1);console.log('PASS: result reported immediately while the next long poll is still waiting.');})().catch(e=>{console.error(e);process.exitCode=1;change({enabled:{newValue:false}},'local');});
`;

async function navigationChecks() {
  let updated;
  context.browser.tabs.onUpdated={addListener(fn){updated=fn;},removeListener(){}};
  const originalGet=context.browser.tabs.get;
  context.browser.tabs.get=async()=>({id:7,url:'about:blank',status:'complete'});
  let done=false;
  const opening=context.waitForTab(7,1000).then(()=>{done=true;});
  await new Promise(resolve=>setTimeout(resolve,10));assert.equal(done,false);
  updated(7,{status:'complete'},{id:7,url:'https://example.org',status:'complete'});await opening;
  context.browser.tabs.get=async()=>({...tab});done=false;
  const reloading=context.waitForTab(7,1000,{previousURL:tab.url,action:async()=>{assert.equal(typeof updated,'function');}}).then(()=>{done=true;});
  await new Promise(resolve=>setTimeout(resolve,10));assert.equal(done,false);
  updated(7,{status:'loading'},{...tab,status:'loading'});updated(7,{status:'complete'},{...tab});await reloading;
  context.browser.tabs.get=originalGet;
  console.log('PASS: navigation ignores initial about:blank and previous complete document.');
}
