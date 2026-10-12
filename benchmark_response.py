"""Measure full/compact MCP text output on isolated real Firefox fixture pages.

Reports aggregate UTF-8 bytes, characters and elapsed time, never page contents.
Byte counts are not tokenizer counts; model-specific tokenization can differ.
Requires a rebuilt MCP zipapp, Firefox desktop and web-ext; no Android profile.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from bridge import api,make_server
from test_attach import Client,close_http_connections
from test_firefox import FixtureHandler

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',help='Optional aggregate-only JSON results path')
    options=parser.parse_args()
    results=[]
    with tempfile.TemporaryDirectory(prefix='bridge-response-size-') as directory,tempfile.TemporaryFile(mode='w+') as logs:
        directory=Path(directory);admin='a'*43;token_file=directory/'admin';token_file.write_text(admin);token_file.chmod(0o600)
        broker=make_server(0,admin);broker_thread=threading.Thread(target=broker.serve_forever);broker_thread.start()
        origin=f'http://127.0.0.1:{broker.server_port}'
        fixture=ThreadingHTTPServer(('127.0.0.1',0),FixtureHandler);fixture_thread=threading.Thread(target=fixture.serve_forever);fixture_thread.start()
        fixture_url=f'http://127.0.0.1:{fixture.server_port}/fixture'
        client=None;runner=None;tabs=[]
        try:
            code=api(origin,admin,'/api/enroll',{'device':'fixture'})['code'];paired=api(origin,'','/api/pair',{'code':code})
            extension=directory/'extension';shutil.copytree(ROOT/'extension',extension)
            bootstrap='''(async()=>{await browser.storage.local.set({enabled:true,connections:[PROFILE]});await browser.tabs.create({url:WARMUP});})();'''.replace('WARMUP',json.dumps(fixture_url+'?warmup')).replace('PROFILE',json.dumps({'id':'benchmark','name':'Isolated benchmark','url':origin,'urls':[origin],'token':paired['token'],'device':'fixture','enabled':True}))
            (extension/'test-bootstrap.js').write_text(bootstrap)
            manifest=json.loads((extension/'manifest.json').read_text());manifest['background']['scripts'].append('test-bootstrap.js');(extension/'manifest.json').write_text(json.dumps(manifest))
            env=os.environ.copy();env.update(MOZ_HEADLESS='1',MOZ_DISABLE_CONTENT_SANDBOX='1',MOZ_DISABLE_RDD_SANDBOX='1',MOZ_DISABLE_GPU_SANDBOX='1')
            runner=subprocess.Popen(['npm','exec','--yes','--package','web-ext@10','--','web-ext','run','--no-config-discovery','--no-input','--no-reload','--source-dir',str(extension),'--firefox','/usr/bin/firefox','--args=-headless'],stdout=logs,stderr=logs,env=env,start_new_session=True)
            deadline=time.monotonic()+60
            while not any(item['online'] for item in broker.broker.handle('/api/devices',{})['devices']):
                if time.monotonic()>deadline or runner.poll() is not None:raise RuntimeError('Isolated Firefox did not connect for response benchmark')
                time.sleep(.1)
            client=Client(origin,token_file,os.environ.copy());initialized=client.rpc('initialize',{'protocolVersion':'2025-03-26'})
            def call(operation,args=None,mode='compact',fields=None):
                arguments={'device':'fixture','op':operation,'args':args or {}}
                if mode is not None:arguments['resultMode']=mode
                if fields is not None:arguments['resultFields']=fields
                started=time.perf_counter();response=client.rpc('tools/call',{'name':'browser_command','arguments':arguments});elapsed=(time.perf_counter()-started)*1000
                if response.get('isError'):raise RuntimeError('Fixture benchmark operation failed: '+json.loads(response['content'][0]['text']).get('code','unknown'))
                text=next(item['text'] for item in response['content'] if item['type']=='text')
                return json.loads(text),{'textBytes':len(text.encode('utf-8')),'textCharacters':len(text),'wireBytes':len(json.dumps(response,ensure_ascii=False,separators=(',',':')).encode('utf-8')),'elapsedMs':round(elapsed,2)}
            for name,suffix in [('interaction-lab',''),('large-generated-dom','?large')]:
                opened,_=call('open',{'url':fixture_url+suffix,'waitUntil':'complete'},'full');tab=opened['id'];tabs.append(tab)
                for operation,args in [('read',{'tabId':tab}),('locate',{'tabId':tab,'role':'button'})]:
                    full,full_size=call(operation,args,'full');compact,compact_size=call(operation,args,None)
                    assert 'elements' in full and 'elements' in compact
                    if operation=='read':
                        assert compact['url']==full['url'] and compact['documentId']==full['documentId']
                        assert compact['textLength']==full['textLength'] and compact['elementCount']==full['elementCount']
                        assert len(compact['text'])<=2000 and len(compact['elements'])<=20
                    else:assert compact['count']==full['count'] and len(compact['elements'])<=20
                    if compact['elements']:
                        ref=compact['elements'][0]['ref'];inspection,_=call('inspect',{'tabId':tab,'ref':ref},'compact');assert inspection['ref']==ref and 'rect' in inspection
                    results.append({'fixture':name,'operation':operation,'full':full_size,'compact':compact_size,'textByteReductionPercent':round((1-compact_size['textBytes']/full_size['textBytes'])*100,2)})
                explicit,_=call('read',{'tabId':tab,'selectors':True,'maxElements':3,'textLimit':321},'compact')
                assert len(explicit['elements'])==3 and len(explicit['text'])<=321 and all('selector' in element for element in explicit['elements'])
                navigation,_=call('read',{'tabId':tab,'text':False,'maxElements':0},'compact');assert navigation['readyState']=='complete' and navigation['documentId']
                call('close',{'tabId':tab},'full');tabs.remove(tab)
            report={'mcpVersion':initialized['serverInfo']['version'],'measurement':'UTF-8 response text bytes; not model tokenizer counts','results':results}
            if options.output:
                destination=Path(options.output);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2))
        except Exception:
            logs.seek(0);messages=logs.read()[-6000:]
            messages=messages.replace(admin,'[redacted]').replace(paired['token'] if 'paired' in locals() else 'never-match','[redacted]')
            print(messages,flush=True)
            raise
        finally:
            if client:
                for tab in tabs:
                    try:client.tool('close',{'tabId':tab})
                    except Exception:pass
                client.close()
            if runner and runner.poll() is None:
                os.killpg(runner.pid,signal.SIGTERM)
                try:runner.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(runner.pid,signal.SIGKILL);runner.wait()
            close_http_connections();fixture.shutdown();fixture.server_close();fixture_thread.join();broker.shutdown();broker.server_close();broker_thread.join()


if __name__=='__main__':main()
