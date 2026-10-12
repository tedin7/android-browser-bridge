#!/usr/bin/env python3
"""Concrete release-gate hooks; only owned fixture tabs, explicit private profiles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
from benchmark_fixture import private_json
from connection import load_connection


def source_identity(root):
    root=Path(root)
    files=sorted([*root.glob('*.py'),*root.glob('operations.json'),*root.joinpath('extension').glob('*.js'),*root.joinpath('extension').glob('manifest.json')])
    if not files or not root.joinpath('mcp_server.py').is_file():raise ValueError('Browser Bridge source checkout required')
    digest=hashlib.sha256()
    for file in files:digest.update(str(file.relative_to(root)).encode()+b'\0'+file.read_bytes()+b'\0')
    return digest.hexdigest()


class MCP:
    def __init__(self,spec):
        profile=load_connection(spec['connectionFile'])
        environment={**os.environ,'BROWSER_BRIDGE_URL':profile['url'],'BROWSER_BRIDGE_TOKEN':profile['token']}
        self.process=subprocess.Popen(spec['mcpCommand'],cwd=spec['repo'],env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        self.responses=queue.Queue();self.id=0
        def read():
            try:
                for line in self.process.stdout:self.responses.put(json.loads(line))
            except (ValueError,OSError):pass
            finally:self.responses.put(None)
        threading.Thread(target=read,daemon=True).start()
        try:
            self.initial=self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'release-fixture-hook','version':'1'}})
        except Exception:
            self.process.terminate();self.process.wait(timeout=2);raise
    def rpc(self,method,params):
        self.id+=1;self.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.id,'method':method,'params':params})+'\n');self.process.stdin.flush()
        response=self.responses.get(timeout=15)
        if not response or response.get('error') or response.get('id')!=self.id:raise ValueError('Fixture MCP request failed')
        return response['result']
    def tool(self,name,args):
        result=self.rpc('tools/call',{'name':name,'arguments':args})
        if result.get('isError'):raise ValueError('Fixture browser action unavailable')
        return json.loads(next(block['text'] for block in result['content'] if block['type']=='text'))
    def command(self,device,op,args=None):return self.tool('browser_command',{'device':device,'op':op,'args':args or {}})
    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=2)


def admin(config,action,identity):
    state=json.loads(Path(config['serverState']).read_text())
    request=Request(state['origin']+'/admin/'+action,data=json.dumps(identity).encode(),headers={'Authorization':'Bearer '+state['token'],'Content-Type':'application/json'})
    with urlopen(request,timeout=5) as response:return json.load(response)


def run_hook(config,action,identity,client_factory=MCP):
    if action not in ('prepare','verify','cleanup'):raise ValueError('Unknown hook')
    spec=config['revisions'][identity['revision']]
    if identity['buildId']!=spec['buildId']:raise ValueError('Requested revision mismatch')
    state_path=Path(config['episodeDirectory'])/(identity['episodeId']+'.json')
    if not isinstance(identity['episodeId'],str) or len(identity['episodeId'])!=20 or any(c not in '0123456789abcdef' for c in identity['episodeId']):raise ValueError('Invalid episode ID')
    origin=config['browserOrigin'].rstrip('/')
    prefix=origin+'/fixture/'+identity['episodeId']+'/'
    if action=='verify':
        result=admin(config,'verify',identity)
        client=client_factory(spec)
        try:
            tracked=json.loads(state_path.read_text())
            checks={}
            for slot,tab in tracked['tabs'].items():
                observed=client.command(spec['device'],'read',{'tabId':tab,'selector':'#status','maxElements':0,'textLimit':500})
                expected={'form':'Saved '+tracked['expectedValue'],'dynamic_filter':'Loaded 3 rows','concurrent_tabs':'Saved '+slot,'uncertain_result':'Verified action '+tracked['actionId']+': effect count 1'}[identity['scenario']]
                checks['visible_'+slot]=observed.get('text','').strip()==expected and observed.get('url','').startswith(prefix)
            result['checks'].update(checks)
            result['verified']=bool(checks) and all(result['checks'].values())
            return result
        finally:client.close()
    if action=='cleanup':
        client=client_factory(spec)
        try:
            # URL ownership permits cleanup even if preparation lost an open response.
            for tab in client.command(spec['device'],'tabs'):
                if tab.get('url','').startswith(prefix):client.command(spec['device'],'close',{'tabId':tab['id']})
        finally:client.close()
        state_path.unlink(missing_ok=True)
        return admin(config,'cleanup',identity)
    if source_identity(spec['repo'])!=spec['buildId']:raise ValueError('Frozen source changed')
    client=client_factory(spec)
    try:
        if client.initial.get('serverInfo',{}).get('version')!=spec['expectedMcpVersion']:raise ValueError('Unexpected MCP runtime version')
        capabilities=client.command(spec['device'],'capabilities')
        if capabilities.get('version')!=spec['expectedExtensionVersion']:raise ValueError('Selected extension does not match this revision')
        prepared=admin(config,'prepare',identity)
        tracked={**prepared,'tabs':{}}
        private_json(state_path,tracked)
        for slot in prepared['slots']:
            opened=client.command(spec['device'],'open',{'url':prefix+slot,'active':True})
            tracked['tabs'][slot]=opened['id'];private_json(state_path,tracked)
        for tab in tracked['tabs'].values():
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                tabs=client.command(spec['device'],'tabs')
                if any(item['id']==tab and item.get('status')=='complete' and item.get('url','').startswith(prefix) for item in tabs):break
                time.sleep(.1)
            else:raise ValueError('Owned fixture did not load')
        context={'device':spec['device'],'tabs':tracked['tabs'],'fixtureUrl':prefix+prepared['slots'][0],
                 'expectedValue':prepared['expectedValue'],'actionId':prepared['actionId'],'fixtureScope':'owned disposable pages only'}
        return {'ready':True,'buildId':spec['buildId'],'context':context}
    finally:client.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('config');parser.add_argument('action',choices=['prepare','verify','cleanup']);args=parser.parse_args()
    try:
        config=json.loads(Path(args.config).read_text());identity=json.loads(sys.stdin.buffer.read(16385))
        print(json.dumps(run_hook(config,args.action,identity)));return 0
    except Exception as error:
        print(json.dumps({'error':'FIXTURE_HOOK_FAILED','errorType':type(error).__name__}));return 1


if __name__=='__main__':raise SystemExit(main())
