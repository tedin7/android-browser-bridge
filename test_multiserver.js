/* Independent broker transport regressions: fixture credentials only, no browser pages. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const manifest=JSON.parse(fs.readFileSync('extension/manifest.json','utf8'));
const a={id:'alpha',name:'Alpha',url:'http://127.0.0.1:19471',urls:['http://127.0.0.1:19471'],token:'fixture-token-alpha',device:'device-alpha',enabled:true};
const b={id:'beta',name:'Beta',url:'http://127.0.0.1:19472',urls:['http://127.0.0.1:19472'],token:'fixture-token-beta',device:'device-beta',enabled:true};
let store={connections:[a,b],enabled:true},changed,statusHandler;
const queues=new Map([[a.url,[]],[b.url,[]]]),pending=new Map(),offline=new Set(),reports=[],executed=[],aborted=new Map(),requested=[],resolvers=new Map();
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(predicate,label){const end=Date.now()+1500;while(!predicate()){if(Date.now()>end)throw Error('Timeout: '+label);await sleep(5);}}
function deliver(origin,command){const request=pending.get(origin);if(request){pending.delete(origin);request.resolve({ok:true,status:200,json:async()=>({command})});}else queues.get(origin).push(command);}
function command(id,tabId,extra={}){return {id,op:'read',args:{tabId,...extra}};}
async function update(values){const changes={};for(const [key,value] of Object.entries(values)){changes[key]={oldValue:store[key],newValue:structuredClone(value)};store[key]=structuredClone(value);}changed(changes,'local');await sleep(0);}
const browser={storage:{local:{get:async()=>structuredClone(store),set:async values=>update(values)},onChanged:{addListener(fn){changed=fn;}}},runtime:{getManifest:()=>manifest,onMessage:{addListener(fn){statusHandler=fn;}},onInstalled:{addListener(){}},openOptionsPage:async()=>{}},browserAction:{onClicked:{addListener(){}}}};
const context=vm.createContext({URL,AbortController,AbortSignal,setTimeout,clearTimeout,performance,structuredClone,console,browser,fetch:async(url,options)=>{
 const origin=new URL(url).origin,profile=origin===a.url?a:b;
 assert.equal(options.headers.Authorization,'Bearer '+profile.token);
 const payload=JSON.parse(options.body);assert.equal(payload.device,profile.device);
 requested.push({origin,path:new URL(url).pathname,id:payload.id});
 if(offline.has(origin))throw Error('Offline fixture broker');
 if(url.endsWith('/api/result')){reports.push({origin,payload});return {ok:true,status:200,json:async()=>({ok:true})};}
 assert(url.endsWith('/api/poll'));
 const queue=queues.get(origin);if(queue.length)return {ok:true,status:200,json:async()=>({command:queue.shift()})};
 return await new Promise((resolve,reject)=>{pending.set(origin,{resolve,reject});options.signal.addEventListener('abort',()=>{if(pending.get(origin)?.resolve===resolve)pending.delete(origin);aborted.set(origin,(aborted.get(origin)||0)+1);reject(Error('Aborted fixture request'));},{once:true});});
}});
for(const file of manifest.background.scripts)vm.runInContext(fs.readFileSync('extension/'+file,'utf8'),context);
context.execute=async request=>{executed.push(request.id);if(request.args.block)await new Promise(resolve=>resolvers.set(request.id,resolve));return {fixture:request.args.source||request.id};};
(async()=>{
 await until(()=>pending.has(a.url)&&pending.has(b.url),'simultaneous independent long polls');
 const legacy=context.normalizeBridgeConnections({url:a.url,token:a.token,device:a.device,enabled:false});
 assert.equal(legacy.length,1);assert.equal(legacy[0].id,'legacy');assert.equal(legacy[0].enabled,true);
 assert.equal(context.normalizeBridgeConnections({connections:[],url:a.url,token:a.token,device:a.device}).length,0);
 deliver(a.url,command('same-id',1,{source:'from-alpha'}));deliver(b.url,command('same-id',2,{source:'from-beta'}));
 await until(()=>reports.length===2,'results from both brokers');
 assert.equal(reports.find(item=>item.origin===a.url).payload.result.fixture,'from-alpha');
 assert.equal(reports.find(item=>item.origin===b.url).payload.result.fixture,'from-beta');
 await until(()=>pending.has(a.url)&&pending.has(b.url),'second independent polls');
 offline.add(a.url);pending.get(a.url).reject(Error('Network unavailable'));pending.delete(a.url);
 deliver(b.url,command('offline-alpha-beta-continues',2));
 await until(()=>reports.some(item=>item.payload.id==='offline-alpha-beta-continues'),'healthy broker continues when other offline');
 offline.delete(a.url);
 await until(()=>pending.has(a.url),'offline broker retries independently');
 deliver(a.url,command('alpha-blocked',1,{block:true}));
 await until(()=>resolvers.has('alpha-blocked')&&pending.has(a.url),'blocked alpha and continued alpha polling');
 deliver(a.url,command('alpha-queued',1));
 await until(()=>requested.some(item=>item.origin===a.url&&item.path==='/api/poll')&&pending.has(a.url),'queued alpha command fetched');
 const betaAborts=aborted.get(b.url)||0;
 await update({connections:[{...a,enabled:false},b]});resolvers.get('alpha-blocked')();
 deliver(b.url,command('beta-after-alpha-disabled',2));
 await until(()=>reports.some(item=>item.payload.id==='beta-after-alpha-disabled'),'disabling alpha preserves beta');
 assert(!executed.includes('alpha-queued'));assert(!reports.some(item=>['alpha-blocked','alpha-queued'].includes(item.payload.id)));
 assert.equal(aborted.get(b.url)||0,betaAborts,'per-profile disable must not abort the other broker');
 await update({connections:[a,b]});await until(()=>pending.has(a.url),'reenabled alpha poll');
 const alphaAborts=aborted.get(a.url)||0;
 await update({connections:[b]});
 await until(()=>(aborted.get(a.url)||0)>alphaAborts,'removed profile aborts its pending poll');
 assert.equal(aborted.get(b.url)||0,betaAborts,'removal must not abort the other broker');
 deliver(b.url,command('beta-after-alpha-removed',2));await until(()=>reports.some(item=>item.payload.id==='beta-after-alpha-removed'),'remaining broker works after removal');
 await until(()=>pending.has(b.url),'beta poll before global pause');
 await update({enabled:false});await until(()=>!pending.has(b.url),'global pause aborts pending requests');
 deliver(b.url,command('paused-command',2));await sleep(20);assert(!executed.includes('paused-command'));
 const status=await statusHandler({type:'status'});assert.equal(status.enabled,false);
 assert(!JSON.stringify(status).includes(a.token));assert(!JSON.stringify(status).includes(b.token));
 await update({enabled:true});await until(()=>reports.some(item=>item.payload.id==='paused-command'),'global resume');
 console.log('PASS: independent simultaneous brokers, credential/result routing, offline isolation, per-profile cancellation/removal, legacy migration and global pause.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await update({enabled:false});await sleep(20);});
