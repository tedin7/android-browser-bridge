const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('extension/operations.generated.js', 'utf8'), context);
const registry = context.BrowserBridgeOperations;
const valid = [
  ['fill', {ref:'e1',value:'hello',expectedDocumentId:'d1'}],
  ['read', {textLimit:0,maxElements:0}],
  ['batch', {tabId:7,workflowId:'flow',leaseGeneration:'g',steps:[{op:'release_lease'}]}],
  ['batch', {tabId:7,steps:[{op:'webmcp_discover'}]}],
];
const invalid = [
  ['fill', {ref:'e1',value:123}], ['read',null], ['read',[]],
  ['read',{textLimit:NaN}], ['read',{maxElements:true}], ['read',{unknown:1}],
  ['batch',{steps:[{op:'open',args:{url:'https://example.org'}},{op:'fill',args:{value:'x'}}]}],
  ['batch',{steps:[{op:'batch',args:{steps:[{op:'tabs'}]}}]}],
  ['batch',{steps:[{op:'release_lease',args:{workflowId:'f',leaseGeneration:'g'}}]}],
  ['__proto__',{}], ['read',{expectedDocumentId:''}]
];
for (const [op,args] of valid) { const before=JSON.stringify(args);registry.validateArguments(op,args);assert.equal(JSON.stringify(args),before); }
for (const [op,args] of invalid) assert.throws(()=>registry.validateArguments(op,args), e=>e.code==='INVALID_ARGUMENT');
assert.throws(()=>registry.validateArguments('viewport',{width:800,height:600},'firefox-android'),/unavailable/);
registry.validateResult('batch',{completed:2,results:[{op:'open',result:{id:7}},{op:'fill',result:{ok:true,length:3}}]});
assert.throws(()=>registry.validateResult('batch',{completed:1,results:[{op:'open',result:{id:'wrong'}}]}),/invalid type/);
assert.throws(()=>registry.validateResult('screenshot',{mimeType:'text/plain',data:'x',tabId:7}),/unsupported value/);
// Admission validates the full batch before any browser mutation.
let writes=0;
const runtime = vm.createContext({URL,AbortController,setTimeout,clearTimeout,performance,browser:{
  tabs:{create:async()=>{writes++;return {id:7};}},storage:{onChanged:{addListener(){}}},runtime:{onMessage:{addListener(){}},onInstalled:{addListener(){}}},browserAction:{onClicked:{addListener(){}}}
}});
vm.runInContext(fs.readFileSync('extension/operations.generated.js','utf8'),runtime);
vm.runInContext(fs.readFileSync('extension/background.js','utf8').replace(/loop\(\);\s*$/,''),runtime);
(async()=>{
 await assert.rejects(runtime.execute({op:'batch',args:{steps:[{op:'open',args:{url:'https://example.org'}},{op:'fill',args:{value:'x'}}]}}),/steps\[1\] fill: args: needs one of selector, ref/);
 assert.equal(writes,0);
 console.log('PASS: generated contract types, bounds, batch inheritance, recursive output contracts and zero mutations on malformed batch.');
})().catch(error=>{console.error(error);process.exitCode=1;});
