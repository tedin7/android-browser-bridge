/* Desktop window calibration uses fixed browser APIs, never remote scripts. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let width=1100,height=800,os='linux',updates=0,freeze=false;
const tab={id:7,windowId:2,url:'https://fixture.example/'};
const ctx=vm.createContext({URL,AbortController,setTimeout,clearTimeout,performance,console,browser:{
 tabs:{get:async()=>tab}, windows:{get:async()=>({width,height}),update:async(id,args)=>{assert.equal(id,2);updates++;width=args.width;height=args.height;}},
 runtime:{getPlatformInfo:async()=>({os}),getManifest:()=>({version:'0.3.1'}),onMessage:{addListener(){}},onInstalled:{addListener(){}}},
 storage:{onChanged:{addListener(){}}},browserAction:{onClicked:{addListener(){}}}}});
vm.runInContext(fs.readFileSync('extension/background.js','utf8').replace(/loop\(\);\s*$/,''),ctx);
ctx.sendPage=async(id,op,args)=>{assert.equal(op,'read');assert.equal(args.text,false);assert.equal(args.maxElements,0);return {viewport:{width:freeze?1060:width-40,height:freeze?710:height-90}};};
(async()=>{
 let result=await ctx.execute({op:'viewport',args:{tabId:7,width:1280,height:720}});
 assert.equal(result.matched,true);assert.equal(result.actual.width,1280);assert.equal(result.actual.height,720);assert.equal(result.attempts,1);assert.equal(updates,1);
 assert.equal(result.affectsWindowTabs,true);assert.equal(result.desktopOnly,true);
 os='android';updates=0;await assert.rejects(ctx.execute({op:'viewport',args:{tabId:7,width:1280,height:720}}),e=>e.code==='UNSUPPORTED_OPERATION');assert.equal(updates,0);
 os='linux';freeze=true;updates=0;result=await ctx.execute({op:'viewport',args:{tabId:7,width:1280,height:720}});
 assert.equal(result.matched,false);assert.equal(result.verified,false);assert.equal(updates,2);assert.equal(result.actual.width,1060);assert(result.nextStep.includes('actual'));
 await assert.rejects(ctx.execute({op:'viewport',args:{tabId:7,width:100,height:720}}),e=>e.code==='INVALID_ARGUMENT');
 console.log('PASS: measured desktop viewport calibration, two-attempt bound, Android rejection and honest unmatched dimensions.');
})().catch(error=>{console.error(error);process.exitCode=1;});
