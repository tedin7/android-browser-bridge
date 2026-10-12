#!/usr/bin/env python3
"""Owned loopback fixture for release_gate; never opens a browser on startup."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

SCENARIOS = {'form', 'dynamic_filter', 'concurrent_tabs', 'uncertain_result'}
PAGE = '''<!doctype html><meta charset="utf-8"><title>Browser Bridge release fixture</title>
<style>body{font:18px system-ui;margin:24px;max-width:700px}label{display:block;margin:16px 0}button,input,select{font:inherit;padding:9px}output{display:block;margin:16px 0}</style>
<h1>Owned release fixture</h1><p id="identity"></p><main id="controls"></main><output id="status" aria-live="polite">Ready</output>
<script>
const config=CONFIG_JSON;
const panel=document.querySelector('#controls'), status=document.querySelector('#status');
document.querySelector('#identity').textContent='Episode '+config.episodeId+' / '+config.slot;
function node(tag,text,parent=panel){const x=document.createElement(tag);if(text)x.textContent=text;parent.append(x);return x;}
function input(label,type='text'){const l=node('label',label),i=node('input','',l);i.type=type;return i;}
async function send(action,data={}){const r=await fetch('/event/'+config.episodeId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,slot:config.slot,...data})});if(!r.ok)throw Error('Fixture rejected event');return r.json();}
if(config.scenario==='form'){
 const f=node('form'),l=node('label','Unique value',f),value=node('input','',l);value.id='value';
 const sl=node('label','Choice',f),choice=node('select','',sl);choice.id='choice';for(const [v,t]of[['alpha','Alpha'],['beta','Beta']]){const o=node('option',t,choice);o.value=v;}
 const cl=node('label','Consent',f),consent=node('input','',cl);consent.type='checkbox';consent.id='consent';
 const b=node('button','Save fixture',f);b.type='submit';b.id='save';
 f.onsubmit=async e=>{e.preventDefault();const r=await send('form',{value:value.value,choice:choice.value,consent:consent.checked});status.textContent=r.saved?'Saved '+r.value:'Not saved';};
}else if(config.scenario==='dynamic_filter'){
 const query=input('Filter');query.id='filter';const b=node('button','Apply filter');b.id='apply';const rows=node('div');rows.id='rows';
 b.onclick=async()=>{status.textContent='Loading';await new Promise(r=>setTimeout(r,250));const r=await send('filter',{query:query.value});rows.replaceChildren();for(const text of r.rows)node('p',text,rows);status.textContent='Loaded '+r.rows.length+' rows';};
}else if(config.scenario==='concurrent_tabs'){
 const value=input('Independent value');value.id='value';const b=node('button','Save tab value');b.id='save';b.onclick=async()=>{const r=await send('tab',{value:value.value});status.textContent='Saved '+r.value;};
}else{
 node('p','Action identity: '+config.actionId);const b=node('button','Commit effect once');b.id='commit';
 b.onclick=async()=>{try{const r=await send('commit',{actionId:config.actionId});status.textContent='Effect '+r.effectCount;}catch{status.textContent='Response lost; outcome unknown. Reconcile action identity before retrying.';}};
 const reconcile=node('button','Reconcile action identity');reconcile.id='reconcile';reconcile.onclick=async()=>{const r=await send('reconcile',{actionId:config.actionId});status.textContent='Verified action '+config.actionId+': effect count '+r.effectCount;};
}
</script>'''


def private_json(path, value):
    path = Path(path); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.fixture-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.episodes = {}

    def prepare(self, identity):
        episode = identity.get('episodeId')
        if not isinstance(episode, str) or len(episode) != 20 or any(c not in '0123456789abcdef' for c in episode) or identity.get('scenario') not in SCENARIOS:
            raise ValueError('Invalid fixture identity')
        with self.lock:
            if episode in self.episodes:
                raise ValueError('Episode already exists; cleanup before reusing')
            entry = {'episodeId': episode, 'scenario': identity['scenario'], 'expected': 'release-'+episode,
                     'actionId': 'effect_'+episode, 'form': None, 'formCount': 0, 'rows': None, 'filter': None,
                     'tabs': {}, 'effectCount': 0, 'faultInjected': False, 'reconciled': False, 'loaded': set()}
            self.episodes[episode] = entry
            return {'episodeId': episode, 'expectedValue': entry['expected'], 'actionId': entry['actionId'], 'slots': ['alpha', 'beta'] if entry['scenario']=='concurrent_tabs' else ['main']}

    def page(self, episode, slot):
        with self.lock:
            entry = self.episodes[episode]
            allowed = ['alpha', 'beta'] if entry['scenario']=='concurrent_tabs' else ['main']
            if slot not in allowed: raise ValueError('Unknown fixture slot')
            entry['loaded'].add(slot)
            config = {key: entry[key] for key in ('episodeId', 'scenario', 'actionId')}; config['slot']=slot
            return PAGE.replace('CONFIG_JSON', json.dumps(config)).encode()

    def event(self, episode, data):
        with self.lock:
            entry = self.episodes[episode]
            action, slot = data.get('action'), data.get('slot')
            if slot not in entry['loaded']: raise ValueError('Fixture page must be loaded')
            if action=='form' and entry['scenario']=='form':
                if not isinstance(data.get('value'), str) or len(data['value'])>512: raise ValueError('Invalid form value')
                entry['form']={key:data.get(key) for key in ('value','choice','consent')};entry['formCount']+=1
                return {'saved':True,'value':data['value']},False
            if action=='filter' and entry['scenario']=='dynamic_filter':
                if not isinstance(data.get('query'),str) or len(data['query'])>100:raise ValueError('Invalid filter')
                entry['filter']=data['query'];entry['rows']=[v for v in ['Alpha one','Beta one','Gamma one','Beta two','Beta three'] if data['query'].lower() in v.lower()]
                return {'rows':entry['rows']},False
            if action=='tab' and entry['scenario']=='concurrent_tabs':
                if not isinstance(data.get('value'),str) or len(data['value'])>100:raise ValueError('Invalid tab value')
                entry['tabs'][slot]=data['value'];return {'value':data['value']},False
            if action in ('commit','reconcile') and entry['scenario']=='uncertain_result':
                if data.get('actionId')!=entry['actionId']:raise ValueError('Action identity mismatch')
                if action=='commit':
                    entry['effectCount']+=1
                    dropped=not entry['faultInjected'];entry['faultInjected']=True
                    return {'effectCount':entry['effectCount']},dropped
                entry['reconciled']=True
                return {'effectCount':entry['effectCount']},False
            raise ValueError('Action outside fixture scenario')

    def verify(self, episode):
        with self.lock:
            e=self.episodes[episode]
            if e['scenario']=='form':checks={'value':e['form']=={'value':e['expected'],'choice':'beta','consent':True},'oneSubmit':e['formCount']==1}
            elif e['scenario']=='dynamic_filter':checks={'filter':e['filter']=='Beta','rows':e['rows']==['Beta one','Beta two','Beta three']}
            elif e['scenario']=='concurrent_tabs':checks={'independentValues':e['tabs']=={'alpha':'alpha','beta':'beta'},'twoPages':e['loaded']=={'alpha','beta'}}
            else:checks={'reconciled':e['reconciled'],'singleEffect':e['effectCount']==1,'responseDropped':e['faultInjected']}
            return {'verified':all(checks.values()),'checks':checks,'faultInjected':e['faultInjected'],'effectCount':e['effectCount']}

    def cleanup(self, episode):
        with self.lock:self.episodes.pop(episode,None)
        return {'cleaned':True}


def make_server(port, token):
    state=State()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value,status=200):
            payload=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_GET(self):
            try:
                parts=urlsplit(self.path).path.split('/')
                if len(parts)!=4 or parts[1]!='fixture':raise ValueError('Unknown path')
                payload=state.page(parts[2],parts[3]);self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            except (ValueError,KeyError):self.reply({'error':'Fixture unavailable'},404)
        def do_POST(self):
            self.connection.settimeout(5)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:raise ValueError('Body limit')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict):raise ValueError('Object required')
                parts=urlsplit(self.path).path.split('/')
                if len(parts)==3 and parts[1]=='admin':
                    if not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token):return self.reply({'error':'Unauthorized'},401)
                    if parts[2]=='prepare':return self.reply(state.prepare(body))
                    if parts[2]=='verify':return self.reply(state.verify(body['episodeId']))
                    if parts[2]=='cleanup':return self.reply(state.cleanup(body['episodeId']))
                if len(parts)==3 and parts[1]=='event':
                    result,drop=state.event(parts[2],body)
                    if drop:
                        self.close_connection=True
                        self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
                    return self.reply(result)
                raise ValueError('Unknown path')
            except (ValueError,KeyError,TypeError):self.reply({'error':'Invalid fixture request'},400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.fixture_state=state;return server


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state-file',required=True);parser.add_argument('--port',type=int,default=0);args=parser.parse_args()
    token=secrets.token_urlsafe(32);server=make_server(args.port,token)
    private_json(args.state_file,{'origin':'http://127.0.0.1:'+str(server.server_port),'token':token})
    print(json.dumps({'ready':True,'stateFile':str(Path(args.state_file).resolve())}),flush=True)
    try:server.serve_forever()
    finally:server.server_close()


if __name__=='__main__':main()
