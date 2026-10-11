"""Two packaged MCP clients share one real broker and one simulated browser."""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from bridge import api, make_server, _http_connections

ROOT=Path(__file__).resolve().parent


def close_http_connections():
    cache=getattr(_http_connections,'cache',{})
    for connection,_ in cache.values():connection.close()
    cache.clear()


class Client:
    def __init__(self,origin,token,environment):
        self.logs=tempfile.TemporaryFile(mode='w+')
        self.process=subprocess.Popen([sys.executable,str(ROOT/'android-browser-mcp.pyz'),'--attach',origin,'--token-file',str(token)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.logs,text=True,env=environment)
        self.responses=queue.Queue();self.identifier=0
        def reader():
            try:
                for line in self.process.stdout:self.responses.put(json.loads(line))
            except Exception as error:self.responses.put(error)
            finally:self.responses.put(None)
        threading.Thread(target=reader,daemon=True).start()
    def send(self,method,params):
        self.identifier+=1
        self.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.identifier,'method':method,'params':params})+'\n');self.process.stdin.flush()
        return self.identifier
    def receive(self,timeout=5):
        try:result=self.responses.get(timeout=timeout)
        except queue.Empty:raise RuntimeError('Attached MCP response timeout') from None
        if result is None:raise RuntimeError('Attached MCP exited')
        if isinstance(result,Exception):raise result
        return result
    def rpc(self,method,params):
        identifier=self.send(method,params);response=self.receive()
        if response['id']!=identifier:raise RuntimeError('Unexpected response identifier')
        if 'error' in response:raise RuntimeError('MCP protocol error')
        return response['result']
    def tool(self,op,args=None):
        return self.rpc('tools/call',{'name':'browser_command','arguments':{'device':'fixture','op':op,'args':args or {}}})
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        self.process.stdout.close();self.logs.close()


class AttachTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.base=Path(self.directory.name)
        self.token=self.base/'admin';self.token.write_text('a'*43);self.token.chmod(0o600)
        self.server=make_server(0,self.token.read_text());self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.server_thread=threading.Thread(target=self.server.serve_forever);self.server_thread.start()
        self.environment=os.environ.copy()
        for key in list(self.environment):
            if key.startswith('BROWSER_BRIDGE_'):self.environment.pop(key)
        self.environment['XDG_STATE_HOME']=str(self.base/'unused-state')
        self.clients=[];self.worker_stop=threading.Event();self.worker_errors=[];self.jobs=[];self.browser=None;self.wait_started=threading.Event();self.wait_release=threading.Event()
    def tearDown(self):
        for client in self.clients:client.close()
        self.worker_stop.set();self.wait_release.set()
        if self.browser:self.browser.join(timeout=2)
        for job in self.jobs:job.join(timeout=2)
        close_http_connections()
        self.server.shutdown();self.server.server_close();self.server_thread.join();self.directory.cleanup()
    def client(self,token=None):
        client=Client(self.url,token or self.token,self.environment);self.clients.append(client)
        initialized=client.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'attach-test','version':'1'}})
        self.assertEqual(initialized['serverInfo']['name'],'android-browser-bridge')
        return client
    def start_browser(self):
        code=api(self.url,self.token.read_text(),'/api/enroll',{'device':'fixture'})['code']
        browser_token=api(self.url,'','/api/pair',{'code':code})['token']
        api(self.url,browser_token,'/api/poll',{'device':'fixture'})
        def reply(command):
            try:
                if command['op']=='wait':self.wait_started.set();self.wait_release.wait(2)
                api(self.url,browser_token,'/api/result',{'device':'fixture','id':command['id'],'result':{'op':command['op'],'tabId':command.get('args',{}).get('tabId')}})
            except Exception as error:self.worker_errors.append(error)
            finally:close_http_connections()
        def browser():
            while not self.worker_stop.is_set():
                try:
                    command=api(self.url,browser_token,'/api/poll',{'device':'fixture','waitMs':100})['command']
                    if command:
                        job=threading.Thread(target=reply,args=(command,));self.jobs.append(job);job.start()
                except Exception as error:self.worker_errors.append(error);close_http_connections();return
            close_http_connections()
        self.browser=threading.Thread(target=browser);self.browser.start()
    def test_two_packaged_clients_share_browser_and_one_exit_does_not_stop_broker(self):
        self.start_browser();first=self.client();second=self.client()
        wait_id=first.send('tools/call',{'name':'browser_command','arguments':{'device':'fixture','op':'wait','args':{'tabId':1,'selector':'#fixture'}}})
        self.assertTrue(self.wait_started.wait(1))
        read=second.tool('read',{'tabId':2});self.assertFalse(read.get('isError'))
        self.assertEqual(json.loads(read['content'][0]['text']),{'op':'read','tabId':2})
        self.assertTrue(first.responses.empty(),'First client must still wait while second client completes');self.wait_release.set()
        waited=first.receive();self.assertEqual(waited['id'],wait_id);self.assertFalse(waited['result'].get('isError'))
        self.assertEqual(json.loads(waited['result']['content'][0]['text']),{'op':'wait','tabId':1})
        first.close();self.clients.remove(first)
        again=second.tool('read',{'tabId':3});self.assertFalse(again.get('isError'))
        self.assertEqual(json.loads(again['content'][0]['text'])['tabId'],3)
        self.assertTrue(api(self.url,self.token.read_text(),'/api/devices',{})['devices'])
        self.assertFalse((self.base/'unused-state').exists());self.assertFalse(self.worker_errors)
    def test_bad_or_missing_credentials_fail_without_creating_local_state(self):
        invalid=self.base/'invalid';invalid.write_text('b'*43);invalid.chmod(0o600)
        client=self.client(invalid)
        failure=client.rpc('tools/call',{'name':'browser_devices','arguments':{}})
        self.assertTrue(failure['isError'])
        self.assertEqual(json.loads(failure['content'][0]['text'])['code'],'UNAUTHORIZED')
        client.close();self.clients.remove(client)
        empty=self.base/'empty';empty.write_text('');empty.chmod(0o600)
        for path in [empty,self.base/'missing']:
            with self.subTest(credential=path.name):
                child=subprocess.run([sys.executable,str(ROOT/'android-browser-mcp.pyz'),'--attach',self.url,'--token-file',str(path)],input='',text=True,capture_output=True,env=self.environment,timeout=5)
                self.assertNotEqual(child.returncode,0)
                self.assertNotIn(self.token.read_text(),child.stdout+child.stderr)
                self.assertNotIn('b'*43,child.stdout+child.stderr)
        self.assertFalse((self.base/'unused-state').exists())
        self.assertEqual(api(self.url,self.token.read_text(),'/api/devices',{})['devices'],[])
    def test_attach_launcher_never_creates_listener_or_stops_existing_broker(self):
        import launcher
        for token in [self.token,self.base/'missing']:
            with self.subTest(credential=token.name),patch.object(sys,'argv',['launcher.py','--attach',self.url,'--token-file',str(token)]),patch.dict(os.environ,self.environment,clear=True),patch('launcher.make_server') as listener,patch('launcher.token_file') as create_token,patch('launcher.mcp_main') as mcp:
                if token.exists():launcher.main();mcp.assert_called_once()
                else:
                    with self.assertRaises((OSError,ValueError,SystemExit)):launcher.main()
                listener.assert_not_called();create_token.assert_not_called()
        self.assertEqual(api(self.url,self.token.read_text(),'/api/devices',{})['devices'],[])


if __name__=='__main__':unittest.main()
