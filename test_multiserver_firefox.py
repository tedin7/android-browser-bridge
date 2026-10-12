"""Two owned brokers control one actual isolated Firefox; never a user profile."""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

from bridge import api,make_server
from test_attach import Client,close_http_connections
from test_firefox import FixtureHandler

ROOT=Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory(prefix='bridge-two-firefox-') as directory,tempfile.TemporaryFile(mode='w+') as logs:
        directory=Path(directory);servers=[];threads=[];clients=[];runner=None;profile_connections=[];tabs=[]
        fixture=ThreadingHTTPServer(('127.0.0.1',0),FixtureHandler)
        fixture_thread=threading.Thread(target=fixture.serve_forever);fixture_thread.start()
        fixture_url=f'http://127.0.0.1:{fixture.server_port}/fixture'
        try:
            for index in range(2):
                token=('a' if index==0 else 'b')*43;token_file=directory/f'admin-{index}';token_file.write_text(token);token_file.chmod(0o600)
                server=make_server(0,token);servers.append(server);thread=threading.Thread(target=server.serve_forever);thread.start();threads.append(thread)
                origin=f'http://127.0.0.1:{server.server_port}'
                code=api(origin,token,'/api/enroll',{'device':'fixture'})['code'];paired=api(origin,'','/api/pair',{'code':code})
                profile_connections.append({'id':f'broker-{index}','name':f'Owned broker {index}','url':origin,'urls':[origin],'token':paired['token'],'device':'fixture','enabled':True})
                client=Client(origin,token_file,os.environ.copy());clients.append(client)
                client.rpc('initialize',{'protocolVersion':'2025-03-26'})
            extension=directory/'extension';shutil.copytree(ROOT/'extension',extension)
            bootstrap='''(async()=>{await browser.storage.local.set({connections:CONNECTIONS,enabled:true});
              await browser.tabs.create({url:FIXTURE});})();'''.replace('CONNECTIONS',json.dumps(profile_connections)).replace('FIXTURE',json.dumps(fixture_url))
            (extension/'test-bootstrap.js').write_text(bootstrap)
            manifest=json.loads((extension/'manifest.json').read_text());manifest['background']['scripts'].append('test-bootstrap.js');(extension/'manifest.json').write_text(json.dumps(manifest))
            env=os.environ.copy();env.update(MOZ_HEADLESS='1',MOZ_DISABLE_CONTENT_SANDBOX='1',MOZ_DISABLE_RDD_SANDBOX='1',MOZ_DISABLE_GPU_SANDBOX='1')
            runner=subprocess.Popen(['npm','exec','--yes','--package','web-ext@10','--','web-ext','run','--no-config-discovery','--no-input','--no-reload','--source-dir',str(extension),'--firefox','/usr/bin/firefox','--args=-headless'],stdout=logs,stderr=logs,env=env,start_new_session=True)
            deadline=time.monotonic()+60
            while not all(any(d['online'] for d in server.broker.handle('/api/devices',{})['devices']) for server in servers):
                if time.monotonic()>deadline or runner.poll() is not None:raise RuntimeError('Two owned brokers did not connect to isolated Firefox')
                time.sleep(.1)
            def op(index,action,args=None):
                response=clients[index].tool(action,args)
                if response.get('isError'):raise RuntimeError('Fixture operation failed: '+json.loads(response['content'][0]['text']).get('code','unknown'))
                return json.loads(response['content'][0]['text'])
            tab=op(0,'open',{'url':fixture_url,'waitUntil':'complete'})['id'];tabs.append(tab)
            op(0,'fill',{'tabId':tab,'selector':'#text','value':'two-owned-brokers-fixture'})
            assert op(1,'inspect',{'tabId':tab,'selector':'#text'})['value']=='two-owned-brokers-fixture'
            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(op,0,'read',{'tabId':tab,'selector':'#summary'})
                second=pool.submit(op,1,'click',{'tabId':tab,'selector':'#click'})
                first.result(timeout=10);second.result(timeout=10)
            assert 'clicks:1' in op(0,'read',{'tabId':tab,'selector':'#click-status'})['text']
            servers[0].broker.handle('/api/revoke',{'device':'fixture'})
            assert op(1,'inspect',{'tabId':tab,'selector':'#text'})['value']=='two-owned-brokers-fixture'
            clients[0].close();clients.pop(0)
            response=clients[0].tool('close',{'tabId':tab});assert not response.get('isError');tabs.remove(tab)
            print('PASS: two independent authenticated brokers and packaged MCP clients share one real Firefox; cross-broker tab actions and revocation isolation.',flush=True)
        except Exception:
            logs.seek(0);messages=logs.read()[-6000:]
            for item in profile_connections:messages=messages.replace(item['token'],'[redacted]')
            messages=messages.replace('a'*43,'[redacted]').replace('b'*43,'[redacted]')
            print(messages,flush=True)
            raise
        finally:
            for client in clients:client.close()
            if runner and runner.poll() is None:
                os.killpg(runner.pid,signal.SIGTERM)
                try:runner.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(runner.pid,signal.SIGKILL);runner.wait()
            close_http_connections();fixture.shutdown();fixture.server_close();fixture_thread.join()
            for server in servers:server.shutdown();server.server_close()
            for thread in threads:thread.join()


if __name__=='__main__':main()
