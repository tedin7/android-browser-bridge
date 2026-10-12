/* Instrumented DOM proves skipped work without claiming performance timings. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let handler, queries=0,textReads=0,rectReads=0,targetName='Target';
const document={title:'Fixture',readyState:'complete',visibilityState:'visible',scrollingElement:{scrollWidth:320,scrollHeight:600},documentElement:{getBoundingClientRect:()=>({width:320})},querySelectorAll:()=>{queries++;return [target];}};
const target={tagName:'BUTTON',nodeType:1,isConnected:true,id:'target',parentElement:null,getRootNode:()=>document,getAttribute:()=>null,hasAttribute:()=>false,matches:s=>s===':disabled',getBoundingClientRect:()=>{rectReads++;return {x:1,y:2,width:30,height:20};},get innerText(){textReads++;return targetName;},querySelectorAll:s=>{queries++;return s==='*'?[]:[target];}};
document.body=target;
const win={visualViewport:null};
const context=vm.createContext({browser:{runtime:{onMessage:{addListener:fn=>handler=fn,removeListener(){}}}},document,window:win,location:{href:'https://fixture.invalid'},innerWidth:320,innerHeight:600,scrollX:0,scrollY:0,getComputedStyle:()=>({display:'block',visibility:'visible'}),CSS:{escape:s=>s},WeakRef,Map,WeakMap,Set});
vm.runInContext(fs.readFileSync('extension/page.js','utf8'),context);
const run=(op,args)=>handler({type:'browser-bridge.command',engineVersion:context.__browserBridgePageVersion,op,args});
(async()=>{
 let out=await run('read',{text:false,maxElements:0});assert(!out.error);assert.equal(queries,0);assert.equal(textReads,0);assert.equal(rectReads,0);
 assert.equal(out.result.elementCount,null);assert.equal(out.result.elementsComplete,false);assert(out.result.documentId);assert.equal(out.result.readyState,'complete');
 out=await run('locate',{selector:'#target',includeHidden:true,selectors:false,responseFields:[]});assert(!out.error);
 assert.equal(rectReads,1);assert.equal(textReads,0);assert.equal(out.result.elements[0].enabled,false);assert.equal(out.result.elements[0].visible,true);assert(out.result.elements[0].ref);assert.equal(out.result.elements[0].rect,undefined);assert.equal(out.result.elements[0].selector,undefined);
 const before=queries;
 out=await run('read',{responseFields:['notAField']});assert.equal(out.error.code,'INVALID_ARGUMENT');assert.equal(queries,before);
 out=await run('locate',{selector:'#target',includeHidden:true});assert(!out.error);assert(out.result.elements[0].rect);assert(out.result.elements[0].selector);assert.equal(out.result.elements[0].accessibleName,'Target');assert(textReads>0);
 out=await run('locate',{selector:'#target',includeHidden:true,selectors:false,responseFields:['rect','selector']});assert(out.result.elements[0].rect);assert.equal(out.result.elements[0].selector,undefined);
 const observed=await run('locate',{selector:'#target',includeHidden:true});
 const ref=observed.result.elements[0].ref;
 targetName='Different control';
 const stale=await run('inspect',{ref});assert.equal(stale.error.code,'STALE_REFERENCE');
 const wrongDocument=await run('click',{selector:'#target',expectedDocumentId:'old-document'});assert.equal(wrongDocument.error.code,'STALE_REFERENCE');
 const refreshed=await run('locate',{selector:'#target',includeHidden:true});assert.equal(refreshed.result.elements[0].accessibleName,'Different control');
 console.log('PASS: metadata skips control/text work, field projection skips unrequested descriptors, required safety/provenance retained, defaults preserved.');
})().catch(error=>{console.error(error);process.exitCode=1;});
