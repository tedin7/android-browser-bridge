/* Actual event sequences and timing of the fixed resident input helpers. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class DOMEvent extends Event {
  constructor(type,init={}) { super(type,{bubbles:init.bubbles,cancelable:init.cancelable});
    for (const [key,value] of Object.entries(init)) if(!['bubbles','cancelable'].includes(key)) Object.defineProperty(this,key,{value,configurable:true}); }
}
class Target extends EventTarget { constructor(){super();this.tagName='CANVAS';this.isConnected=true;this.parentElement=null;this.isContentEditable=false;} focus(){} matches(){return false;} getAttribute(){return null;} getRootNode(){return document;} }
class Input extends Target {constructor(){super();this.tagName='INPUT';this.type='text';this.value='';this.selectionStart=0;this.selectionEnd=0;} setSelectionRange(a,b){this.selectionStart=a;this.selectionEnd=b;} }
const document=new EventTarget(); document.visibilityState='visible';document.documentElement={getBoundingClientRect:()=>({width:800})};
const window=new EventTarget();window.visualViewport=null;
const canvas=new Target(); document.elementFromPoint=()=>canvas;
const context=vm.createContext({console,performance,setTimeout,clearTimeout,Event,KeyboardEvent:DOMEvent,MouseEvent:DOMEvent,PointerEvent:DOMEvent,InputEvent:DOMEvent,
 HTMLInputElement:Input,HTMLTextAreaElement:class extends Target{},HTMLSelectElement:class extends Target{},document,window,innerWidth:800,innerHeight:600,
 addEventListener:window.addEventListener.bind(window),removeEventListener:window.removeEventListener.bind(window),
 browser:{runtime:{onMessage:{addListener(){},removeListener(){}}}}});
let source=fs.readFileSync('extension/page.js','utf8');
source=source.replace('  const listener = message => {',`  actionable=()=>{}; reference=()=>"fixture-ref"; pointer=async()=>({clientX:10,clientY:20,bubbles:true,cancelable:true});
 globalThis.helpers={pressKey,coordinateAction,mouseClick};
 const listener = message => {`);
vm.runInContext(source,context);
const {pressKey,coordinateAction,mouseClick}=context.helpers;
(async()=>{
 let keys=[];canvas.addEventListener('keydown',e=>keys.push(['down',e.key,e.code,e.location,e.shiftKey,performance.now()]));
 canvas.addEventListener('keyup',e=>keys.push(['up',e.key,e.code,e.location,e.shiftKey,performance.now()]));
 await pressKey(canvas,{key:' ',inputMode:'page',durationMs:70});
 assert.equal(keys.length,2);assert.equal(keys[0][2],'Space');assert.equal(keys[1][2],'Space');assert(keys[1][5]-keys[0][5]>=60);
 // auto canvas must dispatch once without attempting editable text insertion.
 keys=[];await pressKey(canvas,{key:'w'});assert.equal(keys.length,2);assert.equal(keys[0][2],'KeyW');
 keys=[];await pressKey(canvas,{key:'Shift',code:'ShiftRight'});assert.equal(keys[0][3],2);assert.equal(keys[0][4],true);assert.equal(keys[1][4],false);
 const input=new Input();await pressKey(input,{key:'x',inputMode:'page'});assert.equal(input.value,'');
 let pointer=[];for(const type of ['pointerdown','pointermove','pointerup','mouseup'])canvas.addEventListener(type,e=>pointer.push([type,e.clientX,e.buttons,performance.now()]));
 await coordinateAction('drag',{x:10,y:20,toX:50,toY:20,steps:4,durationMs:100});
 const down=pointer.find(x=>x[0]==='pointerdown'),up=pointer.find(x=>x[0]==='pointerup');assert(up[3]-down[3]>=90);assert.equal(up[1],50);assert.equal(up[2],0);
 pointer=[];setTimeout(()=>{document.visibilityState='hidden';document.dispatchEvent(new Event('visibilitychange'));},30);
 await assert.rejects(coordinateAction('drag',{x:10,y:20,toX:60,toY:20,steps:3,durationMs:300}),e=>e.code==='INPUT_CANCELED'&&e.actionMayHaveOccurred);
 assert.equal(pointer.filter(e=>e[0]==='pointerup').length,1);assert.equal(pointer.filter(e=>e[0]==='mouseup').length,1);
 document.visibilityState='visible';keys=[];
 setTimeout(()=>window.dispatchEvent(new Event('pagehide')),25);
 await assert.rejects(pressKey(canvas,{key:'F9',inputMode:'page',durationMs:300}),e=>e.code==='INPUT_CANCELED');
 assert.equal(keys.filter(e=>e[0]==='up').length,1);
 const before=keys.length;await assert.rejects(pressKey(canvas,{key:'w',durationMs:5001}),e=>e.code==='INVALID_ARGUMENT');assert.equal(keys.length,before);
 // SVG has no .click(): dispatch a coordinate-bearing click, once.
 let clicks=0;canvas.addEventListener('click',e=>{clicks++;assert.equal(e.clientX,10);});
 await mouseClick(canvas,{},1);assert.equal(clicks,1);
 console.log('PASS: canvas keys/code/location, timed key and drag, cancellation releases once, invalid duration before keydown, SVG fallback.');
})().catch(e=>{console.error(e);process.exitCode=1;});
