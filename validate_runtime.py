#!/usr/bin/env python3
"""Verify runtime workflows on an explicitly selected, owned interaction fixture."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from profile_client import Client


def validate(device,tab):
    client=Client();report={}
    try:
        def command(op,args=None):return client.tool('browser_command',{'device':device,'op':op,'args':args or {}})
        page=command('read',{'tabId':tab,'text':False,'maxElements':0})
        url=urlsplit(page.get('url',''))
        if page.get('title')!='Browser Bridge interaction lab' or url.hostname not in {'127.0.0.1','localhost','::1'} or url.path!='/fixture':
            raise ValueError('Only an explicit owned local interaction fixture is accepted')
        caps=command('capabilities')
        report['extensionVersion']=caps['version']
        start=time.perf_counter()
        receipt=client.tool('browser_step',{'device':device,'plan':{'tabId':tab,'steps':[{'op':'fill','args':{'selector':'#text','value':'Android runtime 1.0 verified'}}],'verify':[{'kind':'value','args':{'selector':'#text'},'expected':'Android runtime 1.0 verified'}]}})
        report['step']={'state':receipt['state'],'singleSampleMs':round((time.perf_counter()-start)*1000,2)}
        first=client.tool('browser_observe',{'device':device,'tabId':tab,'args':{'selector':'#click-status','maxElements':0}})
        command('click',{'tabId':tab,'selector':'#click'})
        delta=client.tool('browser_observe',{'device':device,'tabId':tab,'args':{'selector':'#click-status','maxElements':0},'snapshotId':first['snapshotId']})
        report['observation']={'mode':delta['mode'],'clickState':delta.get('changed',delta.get('data',{})).get('text')}
        meta={'io.modelcontextprotocol/protocolVersion':'2026-07-28','io.modelcontextprotocol/clientCapabilities':{'extensions':{'io.modelcontextprotocol/tasks':{}}}}
        task=client.rpc('tools/call',{'_meta':meta,'name':'browser_step','arguments':{'device':device,'plan':{'tabId':tab,'steps':[{'op':'fill','args':{'selector':'#text','value':'Android durable task verified'}}],'verify':[{'kind':'value','args':{'selector':'#text'},'expected':'Android durable task verified'}]}}})
        identifier=task['taskId'];client.close();client=Client()
        deadline=time.monotonic()+15
        while True:
            task=client.rpc('tasks/get',{'_meta':meta,'taskId':identifier})
            if task['status']!='working' or time.monotonic()>deadline:break
            time.sleep(.1)
        report['task']={'status':task['status'],'reconnectedClient':True,'receiptState':json.loads(task['result']['content'][0]['text'])['state'] if 'result' in task else None}
        report['webmcp']=client.tool('browser_command',{'device':device,'op':'webmcp_discover','args':{'tabId':tab}})
        if report['step']['state']!='verified' or report['task']['receiptState']!='verified':raise RuntimeError('Workflow verification failed')
        report['passed']=True
        return report
    finally:client.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--device',required=True);parser.add_argument('--tab-id',required=True,type=int);parser.add_argument('--output');args=parser.parse_args()
    report=validate(args.device,args.tab_id)
    if args.output:
        target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'w') as stream:os.fchmod(stream.fileno(),0o600);json.dump(report,stream,indent=2)
    print(json.dumps(report,separators=(',',':')))


if __name__=='__main__':main()
