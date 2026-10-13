"""Profile actual Android extension through persistent MCP stdio; fixture pages only."""
import argparse
import base64
import json
import os
import queue
import statistics
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/frame'):
            payload=b'<html><title>Fixture frame</title><body><button id="frame-button" onclick="this.textContent=\'frame:clicked\'">Frame button</button><input id="frame-input"></body></html>'
        else:
            payload=(ROOT/'test_page.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        try: self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError): pass  # Navigation may cancel fixture downloads.

    def log_message(self,*_):
        pass


class MCP:
    def __init__(self,url,token_file):
        env=os.environ.copy()
        env.update(BROWSER_BRIDGE_URL=url,BROWSER_BRIDGE_TOKEN_FILE=str(token_file))
        self.process=subprocess.Popen([sys.executable,str(ROOT/'mcp_server.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        self.responses=queue.Queue()
        def receive():
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
            self.responses.put(None)
        threading.Thread(target=receive,daemon=True).start()
        self.identifier=0
        self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'android-profiler','version':'1'}})

    def rpc(self,method,params):
        self.identifier+=1
        self.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.identifier,'method':method,'params':params})+'\n')
        self.process.stdin.flush()
        try: response=self.responses.get(timeout=50)
        except queue.Empty: raise RuntimeError('MCP timeout')
        if response is None: raise RuntimeError('MCP exited')
        if 'error' in response: raise RuntimeError(str(response['error']))
        return response['result']

    def tool(self,name,args):
        response=self.rpc('tools/call',{'name':name,'arguments':args})
        if response.get('isError'): raise RuntimeError(response['content'][0]['text'])
        for image in (item for item in response['content'] if item['type']=='image'):
            payload=base64.b64decode(image['data'],validate=True)
            assert payload.startswith(b'\x89PNG') or payload.startswith(b'\xff\xd8'), 'Invalid screenshot'
        return json.loads(next(item['text'] for item in response['content'] if item['type']=='text'))

    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--device',required=True,help='Paired device name, as listed by browser_devices')
    parser.add_argument('--url',default='http://127.0.0.1:8766')
    parser.add_argument('--token-file',default=os.path.expanduser('~/.local/state/android-browser-bridge/token'))
    parser.add_argument('--samples',type=int,default=12)
    parser.add_argument('--full-suite',action='store_true',help='Run all fixed browser interactions before profiling; requires extension 0.2.0')
    parser.add_argument('--output',default='state/android-baseline.json')
    args=parser.parse_args()
    fixture=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=fixture.serve_forever,daemon=True).start()
    mcp=MCP(args.url,args.token_file)
    results={}
    tab_id=None
    def operation(op,values=None):
        return mcp.tool('browser_command',{'device':args.device,'op':op,'args':values or {}})
    try:
        devices=mcp.tool('browser_devices',{})['devices']
        if not any(d['id']==args.device and d['online'] for d in devices): raise RuntimeError('Android browser offline')
        url=f'http://127.0.0.1:{fixture.server_port}/fixture'
        if args.full_suite:
            from interaction_suite import run_suite
            def concurrent(first,second):
                ids=[]
                for op,values in [('wait',{'tabId':first,'selector':'#never-exists','timeoutMs':1200}),('read',{'tabId':second})]:
                    mcp.identifier+=1;ids.append(mcp.identifier)
                    mcp.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':mcp.identifier,'method':'tools/call','params':{'name':'browser_command','arguments':{'device':args.device,'op':op,'args':values}}})+'\n')
                mcp.process.stdin.flush()
                responses=[]
                for _ in ids:
                    try: responses.append(mcp.responses.get(timeout=15))
                    except queue.Empty: raise RuntimeError('Parallel MCP timeout')
                assert responses[0]['id']==ids[1] and not responses[0]['result'].get('isError'), 'Page B blocked behind page A'
                assert responses[1]['result'].get('isError')
                print('PASS: Android page B completes while page A waits.',flush=True)
            run_suite(operation,url,concurrent,progress=True)
        tab_id=operation('open',{'url':url,'waitUntil':'complete'})['id']
        operation('read',{'tabId':tab_id})
        for op,values in [('tabs',{}),('read',{'tabId':tab_id}),('click',{'tabId':tab_id,'selector':'#click'}),('fill',{'tabId':tab_id,'selector':'#text','value':'MCP profile input'})]:
            elapsed=[]
            for i in range(args.samples):
                start=time.perf_counter(); operation(op,values); elapsed.append((time.perf_counter()-start)*1000)
            ordered=sorted(elapsed)
            results[op]={'samples':len(elapsed),'medianMs':round(statistics.median(elapsed),2),'p95Ms':round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],2),'minMs':round(min(elapsed),2),'maxMs':round(max(elapsed),2)}
            print(op+': '+json.dumps(results[op]),flush=True)
            output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(results,indent=2)+'\n')
        scrolled=operation('scroll',{'tabId':tab_id,'x':0,'y':500})
        assert abs(scrolled['after']['y']-scrolled['before']['y']-500) <= 1, scrolled
        operation('scroll',{'tabId':tab_id,'x':0,'y':-500})
        operation('activate',{'tabId':tab_id})
        operation('reload',{'tabId':tab_id})
        operation('close',{'tabId':tab_id}); tab_id=None
        results['functional']='Existing operations passed on actual Android Firefox: open,tabs,read,click,fill,scroll,activate,reload,close'
        output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(results,indent=2)+'\n')
        print('Saved measurements: '+str(output),flush=True)
    finally:
        if tab_id is not None:
            try:operation('close',{'tabId':tab_id})
            except Exception:pass
        mcp.close();fixture.shutdown();fixture.server_close()


if __name__=='__main__':main()
