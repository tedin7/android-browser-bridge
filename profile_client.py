"""Measure an installed MCP from this machine, using only our disposable fixture."""
import argparse
import json
import os
import queue
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit


class Client:
    def __init__(self):
        executable=Path(os.environ.get('BROWSER_BRIDGE_CLIENT',str(Path.home()/'.local/share/android-browser-bridge/android-browser-mcp.pyz')))
        self.errors=tempfile.TemporaryFile(mode='w+')
        self.process=subprocess.Popen([sys.executable,str(executable),'--auto'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors,text=True)
        self.responses=queue.Queue();self.identifier=0
        def receive():
            for line in self.process.stdout:self.responses.put(json.loads(line))
            self.responses.put(None)
        threading.Thread(target=receive,daemon=True).start()
        self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'remote-latency-check','version':'1'}})

    def rpc(self,method,params):
        self.identifier+=1
        self.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.identifier,'method':method,'params':params})+'\n');self.process.stdin.flush()
        response=self.responses.get(timeout=50)
        if response is None:raise RuntimeError('Installed MCP exited')
        if 'error' in response:raise RuntimeError('MCP protocol error')
        return response['result']

    def tool(self,name,args=None):
        response=self.rpc('tools/call',{'name':name,'arguments':args or {}})
        if response.get('isError'):raise RuntimeError(response['content'][0]['text'])
        return json.loads(next(item['text'] for item in response['content'] if item['type']=='text'))

    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        self.errors.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=int,default=12)
    args=parser.parse_args()
    if not 1 <= args.samples <= 100:parser.error('samples must be 1–100')
    client=Client()
    try:
        devices=[item for item in client.tool('browser_devices')['devices'] if item['online']]
        if len(devices)!=1:raise RuntimeError('Expected one authorized online browser; select the target before profiling')
        device=devices[0]['id']
        def operation(op,values=None):return client.tool('browser_command',{'device':device,'op':op,'args':values or {}})
        fixtures=[tab for tab in operation('tabs') if tab.get('title')=='Browser Bridge interaction lab' and urlsplit(tab.get('url','')).hostname in {'127.0.0.1','::1','localhost'} and urlsplit(tab.get('url','')).path=='/fixture']
        if len(fixtures)!=1:raise RuntimeError('Open exactly one disposable Browser Bridge interaction fixture first; private tabs will not be profiled')
        tab=fixtures[0]['id']
        output={}
        for op,values in [('tabs',{}),('read',{'tabId':tab}),('click',{'tabId':tab,'selector':'#click'}),('fill',{'tabId':tab,'selector':'#text','value':'MCP performance fixture'})]:
            times=[]
            for _ in range(args.samples):
                begin=time.perf_counter();operation(op,values);times.append((time.perf_counter()-begin)*1000)
            ordered=sorted(times)
            output[op]={'samples':len(times),'medianMs':round(statistics.median(times),2),'p95Ms':round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],2)}
        print(json.dumps(output,indent=2))
    finally:client.close()


if __name__=='__main__':main()
