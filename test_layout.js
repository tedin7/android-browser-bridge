/* Fixed-engine inspection: layout is optional, scoped and never performs an action. */
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
let handler, hitCalls = 0, hit = null;
const attributes = new Map(), style = {position:'sticky',top:'12px',right:'auto',bottom:'auto',left:'auto',zIndex:'3',display:'block',visibility:'visible',overflowX:'hidden',overflowY:'auto'};
let rect = {x:20,y:20,left:20,top:20,right:120,bottom:60,width:100,height:40};
const document = {querySelectorAll:()=>[target],getElementById:()=>null,activeElement:null,elementFromPoint:()=>{hitCalls++;return hit;}};
const target = {id:'target',tagName:'DIV',nodeType:1,isConnected:true,isContentEditable:false,parentElement:null,innerText:'Fixture target',clientWidth:100,clientHeight:40,scrollWidth:300,scrollHeight:500,
  getAttribute:key=>attributes.get(key)||null,hasAttribute:key=>attributes.has(key),matches:()=>false,getRootNode:()=>document,getBoundingClientRect:()=>({...rect})};
const context = vm.createContext({browser:{runtime:{onMessage:{addListener:fn=>handler=fn,removeListener(){}}}},WeakRef,Map,WeakMap,Set,Math,Error,Number,String,Boolean,URL,HTMLSelectElement:class{},getComputedStyle:()=>style,
  document,location:{href:'https://fixture.invalid'},CSS:{escape:value=>value},innerWidth:320,innerHeight:600,window:{visualViewport:{width:320,height:600,offsetLeft:0,offsetTop:0}}});
vm.runInContext(fs.readFileSync('extension/page.js','utf8'),context);
const inspect = args => handler({type:'browser-bridge.command',engineVersion:context.__browserBridgePageVersion,op:'inspect',args:{selector:'#target',...args}});
(async()=>{
 hit=target;
 const ordinary=await inspect({});assert(!ordinary.error);assert.equal(ordinary.result.layout,undefined);assert.equal(hitCalls,0);
 let response=await inspect({layout:true});assert(!response.error);let layout=response.result.layout;
 assert.equal(layout.position,'sticky');assert.equal(layout.top,'12px');assert.equal(layout.overflowY,'auto');assert.equal(layout.clientWidth,100);assert.equal(layout.scrollWidth,300);
 assert.equal(layout.inViewport,true);assert.equal(layout.centerInViewport,true);assert.equal(layout.hitTest,true);assert.equal(layout.occluded,false);assert.equal(layout.hitTestPerformed,true);
 hit={parentElement:null,getRootNode:()=>document};layout=(await inspect({layout:true})).result.layout;assert.equal(layout.hitTest,false);assert.equal(layout.occluded,true);
 rect={x:20,y:900,left:20,top:900,right:120,bottom:940,width:100,height:40};const previousCalls=hitCalls;layout=(await inspect({layout:true})).result.layout;
 assert.equal(layout.inViewport,false);assert.equal(layout.centerInViewport,false);assert.equal(layout.hitTest,false);assert.equal(layout.hitTestPerformed,false);assert.equal(layout.occluded,null);assert.equal(hitCalls,previousCalls);
 rect={x:20,y:20,left:20,top:20,right:120,bottom:60,width:100,height:40};hit=null;layout=(await inspect({layout:true})).result.layout;assert.equal(layout.hitTestPerformed,true);assert.equal(layout.occluded,null);
 const child={parentElement:target,getRootNode:()=>document};hit={shadowRoot:{elementFromPoint:()=>child}};layout=(await inspect({layout:true})).result.layout;assert.equal(layout.hitTest,true);assert.equal(layout.occluded,false);
 style.visibility='hidden';const beforeHidden=hitCalls;layout=(await inspect({layout:true})).result.layout;assert.equal(layout.hitTestPerformed,false);assert.equal(layout.occluded,null);assert.equal(hitCalls,beforeHidden);
 assert.equal(target.clientWidth,100);assert.equal(target.scrollHeight,500);
 console.log('PASS: optional scoped CSS layout, center occlusion, offscreen/hidden/unknown safety, open-shadow descendant hits and unchanged default inspection.');
})().catch(error=>{console.error(error);process.exitCode=1;});
