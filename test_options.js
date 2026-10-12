/* Options workflow regression, with fixture-only storage/network and a small DOM. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
 constructor(tag='div',id=''){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.listeners={};this.dataset={};this.attributes={};this.value='';this.checked=false;this.hidden=false;this.disabled=false;this.className='';this._text='';this.classList={add:()=>{},remove:()=>{},toggle:()=>{}};}
 get textContent(){return this._text+this.children.map(child=>typeof child==='string'?child:child.textContent).join('');}
 set textContent(value){this._text=String(value);this.children=[];}
 append(...children){for(const child of children){this.children.push(child);if(typeof child==='object')child.parentElement=this;}}
 appendChild(child){this.append(child);return child;}
 replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
 setAttribute(key,value){this.attributes[key]=String(value);}
 getAttribute(key){return this.attributes[key]??null;}
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
 async fire(type){for(const fn of this.listeners[type]||[])await fn({preventDefault(){},target:this});}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);}
 querySelectorAll(selector){return descendants(this).filter(el=>matches(el,selector));}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
function descendants(root){return root.children.flatMap(child=>typeof child==='object'?[child,...descendants(child)]:[]);}
function matches(el,selector){if(selector.startsWith('#'))return el.id===selector.slice(1);if(selector.startsWith('.'))return el.className.split(/\s+/).includes(selector.slice(1));const role=selector.match(/^\[data-role="([^"]+)"\]$/);if(role)return el.dataset.role===role[1];return el.tagName.toLowerCase()===selector;}
function pairing(origin,code='a1b2c3-d4e5f6'){return 'BB1.'+Buffer.from(JSON.stringify({url:origin,urls:[],code})).toString('base64url');}
function environment(initial){
 let store=structuredClone(initial),changes,sequence=0,fetches=[];
 const ids=[...fs.readFileSync('extension/options.html','utf8').matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
 const elements=new Map(ids.map(id=>[id,new Element(id==='config'?'form':id==='add'||id==='global-toggle'?'button':'div',id)]));
 const document={getElementById:id=>elements.get(id)||null,createElement:tag=>new Element(tag),createTextNode:text=>String(text),querySelectorAll:()=>[],documentElement:{lang:'en'},body:new Element('body'),addEventListener(){}};
 const browser={storage:{local:{get:async()=>structuredClone(store),set:async values=>{if(environment.writeFailure)throw Error('Fixture storage failed');const update={};for(const [key,value] of Object.entries(values)){update[key]={oldValue:store[key],newValue:structuredClone(value)};store[key]=structuredClone(value);}if(changes)changes(update,'local');},remove:async keys=>{for(const key of keys)delete store[key];}},onChanged:{addListener(fn){changes=fn;}}},runtime:{sendMessage:async()=>({enabled:store.enabled===true,connections:[]})}};
 const context=vm.createContext({document,browser,URL,AbortController,AbortSignal,TextDecoder,console,navigator:{language:'en',languages:['en']},crypto:{randomUUID:()=>`fixture-id-${++sequence}`},atob:value=>Buffer.from(value,'base64').toString('binary'),setInterval:()=>0,clearInterval(){},setTimeout,clearTimeout,confirm:()=>true,fetch:async(url,options)=>{
  fetches.push({url,body:JSON.parse(options.body)});
  if(environment.networkFailure)throw Error('NetworkError: unavailable fixture server');
  return {ok:true,status:200,json:async()=>{if(environment.bodyTimeout)return await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted fixture response body')),{once:true}));return {token:'fixture-private-token-'+new URL(url).port,device:'fixture-device'};}};
 }});
 context.window=context;
 for(const file of ['connection.js','connections.js','options.js'])vm.runInContext(fs.readFileSync('extension/'+file,'utf8'),context);
 return {context,elements,fetches,get store(){return store;},async add(origin,name='New owned server',consent=true){elements.get('code').value=pairing(origin);elements.get('name').value=name;elements.get('consent').checked=consent;await context.addPairing();},async settle(){await new Promise(resolve=>setTimeout(resolve,10));}};
}
(async()=>{
 const legacy={url:'http://127.0.0.1:19471',urls:['http://127.0.0.1:19471'],token:'legacy-private-token',device:'legacy-device',enabled:false};
 const ui=environment(legacy);await ui.settle();
 assert.equal(ui.fetches.length,0,'opening settings must not pair or probe brokers');
 await ui.add('http://127.0.0.1:19472');await ui.settle();
 assert(Array.isArray(ui.store.connections),ui.elements.get('form-status').textContent);
 assert.equal(ui.store.connections.length,2,'pairing another server must retain legacy connection');
 assert.equal(ui.store.enabled,false,'adding another server must not silently resume a globally paused browser');
 assert(ui.store.connections.some(profile=>profile.token===legacy.token));
 assert(!('token' in ui.store));assert(!('url' in ui.store));assert(!('device' in ui.store));
 const count=ui.store.connections.length;await ui.add('http://127.0.0.1:19472','Renamed owned server');await ui.settle();
 assert.equal(ui.store.connections.length,count,'re-pairing same broker/device must not duplicate a connection');
 const preserved=JSON.stringify(ui.store);const requests=ui.fetches.length;
 await ui.add('http://127.0.0.1:19473','Consent denied',false);await ui.settle();
 assert.equal(JSON.stringify(ui.store),preserved);assert.equal(ui.fetches.length,requests,'missing consent must not contact server');
 ui.elements.get('consent').checked=true;ui.elements.get('code').value='BB1.invalid';
 await ui.context.addPairing();await ui.settle();assert.equal(JSON.stringify(ui.store),preserved);assert.equal(ui.fetches.length,requests);
 environment.networkFailure=true;await ui.add('http://127.0.0.1:19474');environment.networkFailure=false;await ui.settle();
 assert.equal(JSON.stringify(ui.store),preserved);assert(/check|verify|try again/i.test(ui.elements.get('form-status').textContent),'network failure must offer meaningful recovery guidance');
 assert.equal(ui.elements.get('form-status').dataset.tone,'error');
 environment.writeFailure=true;await ui.add('http://127.0.0.1:19475');environment.writeFailure=false;await ui.settle();
 assert.equal(JSON.stringify(ui.store),preserved,'failed storage must preserve all existing connections');assert.equal(ui.elements.get('code').value,'','used pairing code must be cleared after failed save');assert(/new|retry/i.test(ui.elements.get('form-status').textContent));
 assert.throws(()=>ui.context.parsePairing(pairing('http://public-plain-http.example'),''));
 const beforeBody=ui.fetches.length;environment.bodyTimeout=true;ui.context.setTimeout=(fn,ms)=>setTimeout(fn,ms===15000?5:ms);
 ui.elements.get('code').value='BB1.'+Buffer.from(JSON.stringify({url:'http://127.0.0.1:19476',urls:['http://127.0.0.1:19477'],code:'a1b2c3-d4e5f6'})).toString('base64url');ui.elements.get('consent').checked=true;
 await ui.context.addPairing();environment.bodyTimeout=false;await ui.settle();
 assert.equal(ui.fetches.length,beforeBody+1,'response-body timeout must not replay a potentially consumed pair code on fallback endpoint');assert.equal(ui.elements.get('code').value,'');assert.equal(JSON.stringify(ui.store),preserved);
 const rendered=[...ui.elements.values()].map(el=>el.textContent).join(' ');
 for(const profile of ui.store.connections){assert(!rendered.includes(profile.token),'credential must never be rendered');assert(![...ui.elements.values()].some(el=>String(el.value).includes(profile.token)),'credential must not populate form values');}
 const cards=ui.elements.get('connections').children.filter(child=>typeof child==='object');assert.equal(cards.length,2);
 const controls=descendants(cards[0]);const toggle=controls.find(el=>el.tagName==='BUTTON'&&el.className.includes('button-secondary'));
 assert(toggle,'each saved server needs an individual control');const otherBefore=JSON.stringify(ui.store.connections[1]);await toggle.fire('click');await ui.settle();
 assert.equal(ui.store.connections[0].enabled,false);assert.equal(JSON.stringify(ui.store.connections[1]),otherBefore);
 await ui.elements.get('global-toggle').fire('click');await ui.settle();assert.equal(ui.store.enabled,true);assert.equal(ui.store.connections[0].enabled,false,'global resume must preserve per-server pause');
 const retained=structuredClone(ui.store.connections[1]);await ui.context.removeConnection(ui.store.connections[0].id);await ui.settle();assert.equal(ui.store.connections.length,1);assert.deepEqual(ui.store.connections[0],retained);
 console.log('PASS: options pairing preserves existing servers, consent and validation prevent writes, legacy credentials are removed, duplicate repair is bounded, controls preserve other servers and secrets stay hidden.');
})().catch(error=>{console.error(error);process.exitCode=1;});
