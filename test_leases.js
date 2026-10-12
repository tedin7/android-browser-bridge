/* Real fixed dispatcher, shared extension, two authorized broker connections. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let clock=100, writes=0;
const context=vm.createContext({URL,setTimeout,clearTimeout,AbortController,performance:{now:()=>clock},console,
 browser:{tabs:{get:async id=>({id,url:'https://example.org',windowId:1}),query:async()=>[{id:7,url:'https://example.org'}],sendMessage:async(id,m)=>{if(m.op==='fill')writes++;return {result:{ok:true}};}},storage:{onChanged:{addListener(){}}},runtime:{getManifest:()=>({version:'1.0.0'}),onMessage:{addListener(){}},onInstalled:{addListener(){}}},browserAction:{onClicked:{addListener(){}}}}});
vm.runInContext(fs.readFileSync('extension/operations.generated.js','utf8'),context);
vm.runInContext(fs.readFileSync('extension/background.js','utf8').replace(/loop\(\);\s*$/,''),context);
const owners=vm.runInContext(`config.enabled=true;
['a','b'].map(id=>{const runtime={active:true,requests:new Set(),results:[],outstanding:0};connectionRuntimes.set(id,runtime);return {connectionId:id,runtime};});`,context);
const [a,b]=owners;
const call=(op,args,owner=a)=>context.execute({op,args:op === "fill" ? {selector:"input",...args} : args},owner);
(async()=>{
 await assert.rejects(call('acquire_lease',{workflowId:'flow'}),e=>e.code==='INVALID_ARGUMENT');
 await assert.rejects(call('acquire_lease',{tabId:7,workflowId:'flow',ttlMs:60001}),e=>e.code==='INVALID_ARGUMENT');
 const lease=await call('acquire_lease',{tabId:7,workflowId:'flow',ttlMs:100});
 const held={tabId:7,workflowId:'flow',leaseGeneration:lease.leaseGeneration};
 await assert.rejects(call('fill',{tabId:7},b),e=>e.code==='TAB_LEASED');
 await assert.rejects(call('fill',held,b),e=>e.code==='LEASE_STALE');
 await assert.rejects(call('fill',{tabId:7},a),e=>e.code==='TAB_LEASED');
 assert.equal(writes,0);
 assert((await call('read',{tabId:7},b)).ok);
 await call('fill',held);assert.equal(writes,1);
 const batch=await call('batch',{...held,steps:[{op:'fill',args:{selector:'input'}},{op:'read'}]});assert.equal(batch.completed,2);assert.equal(writes,2);
 const renewed=await call('acquire_lease',{...held,ttlMs:200});assert.equal(renewed.leaseGeneration,held.leaseGeneration);
 await assert.rejects(call('acquire_lease',{tabId:7,workflowId:'other'},b),e=>e.code==='TAB_LEASED');
 clock=301;
 await assert.rejects(call('fill',held),e=>e.code==='LEASE_STALE');
 await assert.rejects(call('acquire_lease',held),e=>e.code==='LEASE_STALE');
 const newer=await call('acquire_lease',{tabId:7,workflowId:'other'},b);
 assert.notEqual(newer.leaseGeneration,held.leaseGeneration);
 await assert.rejects(call('release_lease',held),e=>e.code==='LEASE_STALE');
 await assert.rejects(call('fill',held),e=>e.code==='LEASE_STALE');
 await call('release_lease',{tabId:7,workflowId:'other',leaseGeneration:newer.leaseGeneration},b);
 await call('fill',{tabId:7},a);assert.equal(writes,3);
 await call('acquire_lease',{tabId:7,workflowId:'flow'});
 a.runtime.active=false;
 await call('fill',{tabId:7},b);assert.equal(writes,4);
 console.log('PASS: cross-broker lease isolation, reads allowed, owner proof, renewal/expiry fencing, batch propagation, release and revoked-owner cleanup.');
})().catch(error=>{console.error(error);process.exitCode=1;});
