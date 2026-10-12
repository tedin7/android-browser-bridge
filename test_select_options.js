/* read/locate carry select options so agents skip an inspect turn. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let handler;
const document={title:'Fixture',readyState:'complete',visibilityState:'visible',scrollingElement:{scrollWidth:320,scrollHeight:600},documentElement:{getBoundingClientRect:()=>({width:320})},querySelectorAll:()=>[target]};
const options=[{value:'alpha',text:'Alpha',selected:true,disabled:false},{value:'beta',text:'Beta',selected:false,disabled:false},{value:'x',text:'x',selected:false,disabled:false}];
const target={tagName:'SELECT',type:'select-one',name:'kind',options,nodeType:1,isConnected:true,id:'kind',parentElement:null,getRootNode:()=>document,getAttribute:()=>null,hasAttribute:()=>false,matches:()=>false,getBoundingClientRect:()=>({x:1,y:2,width:30,height:20}),innerText:'Kind',querySelectorAll:s=>s==='*'?[]:[target]};
document.body=target;
const win={visualViewport:null};
const context=vm.createContext({browser:{runtime:{onMessage:{addListener:fn=>handler=fn,removeListener(){}}}},document,window:win,location:{href:'https://fixture.invalid'},innerWidth:320,innerHeight:600,scrollX:0,scrollY:0,getComputedStyle:()=>({display:'block',visibility:'visible'}),CSS:{escape:s=>s},WeakRef,Map,WeakMap,Set});
vm.runInContext(fs.readFileSync('extension/page.js','utf8'),context);
const run=(op,args)=>handler({type:'browser-bridge.command',engineVersion:context.__browserBridgePageVersion,op,args});
(async()=>{
 let out=await run('locate',{selector:'#kind',selectors:false,responseFields:['accessibleName','type']});
 assert(!out.error,JSON.stringify(out.error));
 assert.equal(JSON.stringify(out.result.elements[0].options),JSON.stringify([{value:'alpha',text:'Alpha',selected:true},{value:'beta',text:'Beta'},'x']));
 out=await run('locate',{selector:'#kind',selectors:false,responseFields:['accessibleName']});
 assert(!out.error);assert.equal(out.result.elements[0].options,undefined);
 out=await run('locate',{selector:'#kind',selectors:false,responseFields:['options']});
 assert(!out.error);assert.equal(out.result.elements[0].options.length,3);
 console.log('select options ok');
})().catch(error=>{console.error(error);process.exit(1);});
