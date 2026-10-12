#!/usr/bin/env python3
"""Audit explicit URLs through Browser Bridge MCP in an isolated Firefox desktop.

Resizes only the temporary browser window; no Playwright, arbitrary page scripts,
user profiles, existing broker credentials or screenshots unless requested.
Requires Firefox desktop and npm/web-ext. Reports measured viewport sizes.
"""
import argparse
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from bridge import api, make_server, _http_connections

ROOT = Path(__file__).resolve().parent


class AuditFailure(RuntimeError):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail.get('code', 'AUDIT_FAILED'))


class MCPClient:
    def __init__(self, origin, token_path, logs):
        environment = {key: value for key, value in os.environ.items() if not key.startswith('BROWSER_BRIDGE_')}
        environment.update(BROWSER_BRIDGE_URL=origin, BROWSER_BRIDGE_TOKEN_FILE=str(token_path))
        self.process = subprocess.Popen([sys.executable, str(ROOT/'mcp_server.py')], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=logs, text=True, env=environment)
        self.identifier = 0
        self.responses = queue.Queue()
        def reader():
            try:
                for line in self.process.stdout:
                    self.responses.put(json.loads(line))
            finally:
                self.responses.put(None)
        threading.Thread(target=reader, daemon=True).start()
    def rpc(self, method, params):
        self.identifier += 1
        self.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.identifier,'method':method,'params':params})+'\n')
        self.process.stdin.flush()
        try:
            reply = self.responses.get(timeout=45)
        except queue.Empty:
            raise RuntimeError('Isolated MCP response timed out') from None
        if not isinstance(reply,dict) or reply.get('id') != self.identifier or 'error' in reply:
            raise RuntimeError('Isolated MCP returned an invalid response')
        return reply['result']
    def command(self, operation, args=None, fields=None):
        arguments = {'device':'desktop-audit','op':operation,'args':args or {}}
        if fields is not None:
            arguments.update(resultMode='fields',resultFields=fields)
        reply = self.rpc('tools/call', {'name':'browser_command','arguments':arguments})
        value = json.loads(next(item['text'] for item in reply['content'] if item['type']=='text'))
        if reply.get('isError'):
            raise AuditFailure(value)
        return value, [item for item in reply['content'] if item['type']=='image']
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate(); self.process.wait(timeout=5)
        self.process.stdout.close()


@contextmanager
def isolated_firefox(firefox='/usr/bin/firefox', debug=False):
    """Automatic opt-in applies exclusively to this temporary test extension."""
    with tempfile.TemporaryDirectory(prefix='bridge-desktop-audit-') as directory, tempfile.TemporaryFile(mode='w+') as logs:
        directory = Path(directory)
        admin = secrets.token_urlsafe(32)
        token = directory/'admin'; token.write_text(admin); token.chmod(0o600)
        broker = make_server(0,admin)
        diagnostics = []
        secret_values = [admin]
        diagnostic_path = '/__audit_diagnostic_' + secrets.token_hex(16)
        if debug:
            original_handler = broker.RequestHandlerClass
            class DiagnosticHandler(original_handler):
                def do_POST(self):
                    if self.path != diagnostic_path:
                        return super().do_POST()
                    try:
                        length = int(self.headers.get('Content-Length','0'))
                        if not 0 < length <= 4096:
                            return self.reply(400,{'error':'Invalid diagnostic size'})
                        value = json.loads(self.rfile.read(length))
                        safe = {}
                        for key in ('phase','error'):
                            if isinstance(value.get(key),str):
                                text = value[key]
                                for secret in secret_values:
                                    text = text.replace(secret,'[redacted]')
                                safe[key] = re.sub(r'[A-Za-z0-9_-]{30,}','[redacted]',text)[:200]
                        for key in ('enabled','connected','backgroundReady','statusReceived'):
                            if isinstance(value.get(key),bool): safe[key] = value[key]
                        for key in ('profiles','workers'):
                            if isinstance(value.get(key),int): safe[key] = max(0,min(16,value[key]))
                        errors = value.get('errors',[])
                        if isinstance(errors,list):
                            safe['errors'] = []
                            for item in errors[:16]:
                                if not isinstance(item,str): continue
                                text = item
                                for secret in secret_values: text = text.replace(secret,'[redacted]')
                                safe['errors'].append(re.sub(r'[A-Za-z0-9_-]{30,}','[redacted]',text)[:200])
                        diagnostics.append(safe)
                        return self.reply(200,{'ok':True})
                    except (ValueError,TypeError):
                        return self.reply(400,{'error':'Invalid diagnostic'})
            broker.RequestHandlerClass = DiagnosticHandler
        owner = threading.Thread(target=broker.serve_forever); owner.start()
        origin = f'http://127.0.0.1:{broker.server_port}'
        runner = client = None
        try:
            code = api(origin,admin,'/api/enroll',{'device':'desktop-audit'})['code']
            secret_values.append(code)
            extension = directory/'extension'; shutil.copytree(ROOT/'extension',extension)
            profile = {'id':'desktop-audit','name':'Isolated desktop audit','url':origin,'urls':[origin],
                'device':'desktop-audit','enabled':True}
            bootstrap = r"""(async()=>{
  const report=async value=>{if(DEBUG)try{await fetch(DIAG,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value),signal:AbortSignal.timeout(3000)});}catch(_){};};
  try {
    await report({phase:"bootstrap-loaded",backgroundReady:typeof syncConnections==="function"});
    // Finish the controller's initial storage read before installing fixture
    // credentials. This is local harness setup, not a remotely supplied action.
    if(typeof loop==="function") await loop();
    const response=await fetch(ORIGIN+"/api/pair",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({code:CODE}),signal:AbortSignal.timeout(15000)});
    if(!response.ok) throw Error("Owned fixture pairing failed: HTTP "+response.status);
    const paired=await response.json();
    await browser.storage.local.set({enabled:true,connections:[{...PROFILE,token:paired.token,device:paired.device}]});
    const saved=await browser.storage.local.get(["enabled","connections"]);
    await report({phase:"storage-written",enabled:saved.enabled===true,profiles:saved.connections?.length||0});
    await browser.tabs.create({url:ORIGIN+"/"});
    await new Promise(resolve=>setTimeout(resolve,1200));
    const workers=typeof connectionRuntimes!=="undefined"?[...connectionRuntimes.values()]:[];
    await report({phase:"background-status",enabled:typeof config!=="undefined"&&config.enabled===true,workers:workers.length,connected:workers.some(worker=>worker.connected),errors:workers.map(worker=>worker.error)});
  } catch(error) {await report({phase:"bootstrap-error",error:String(error.message)});}
})();""".replace('DEBUG',json.dumps(debug)).replace('DIAG',json.dumps(origin+diagnostic_path)).replace('PROFILE',json.dumps(profile)).replace('ORIGIN',json.dumps(origin)).replace('CODE',json.dumps(code))
            (extension/'test-bootstrap.js').write_text(bootstrap)
            manifest = json.loads((extension/'manifest.json').read_text()); manifest['background']['scripts'].append('test-bootstrap.js')
            readiness_script = r"""setTimeout(async()=>{
  let value={phase:"page-runtime-status"};
  try {const status=await browser.runtime.sendMessage({type:"status"});value={...value,statusReceived:!!status,connected:!!status?.connected,enabled:!!status?.enabled,profiles:status?.connections?.length||0,errors:(status?.connections||[]).map(item=>item.error||"")};}
  catch(error){value.error=String(error.message);}
  if(DEBUG)try {await fetch(DIAG,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value),signal:AbortSignal.timeout(3000)});}catch(_){}
},1500);""".replace('DIAG',json.dumps(origin+diagnostic_path)).replace('DEBUG',json.dumps(debug))
            # This fixed readiness ping comes from the visible owned warmup
            # page, rather than messaging the background from its own frame.
            (extension/'test-ready-page.js').write_text(readiness_script)
            manifest['content_scripts'].append({'matches':[origin+'/*'],'js':['test-ready-page.js'],'run_at':'document_idle'})
            (extension/'manifest.json').write_text(json.dumps(manifest))
            environment = os.environ.copy()
            environment.update(MOZ_HEADLESS='1')
            runner = subprocess.Popen(['npm','exec','--yes','--package','web-ext@10','--','web-ext','run',
                '--no-config-discovery','--no-input','--no-reload','--source-dir',str(extension),'--firefox',firefox,'--args=-headless'],
                stdout=logs,stderr=logs,env=environment,start_new_session=True)
            deadline = time.monotonic()+60
            while not any(device['online'] for device in broker.broker.handle('/api/devices',{})['devices']):
                if time.monotonic()>deadline or runner.poll() is not None:
                    logs.seek(0)
                    details = logs.read()[-4000:] if debug else ''
                    for secret in secret_values: details = details.replace(secret,'[redacted]')
                    details = re.sub(r'[A-Za-z0-9_-]{30,}','[redacted]',details)
                    raise RuntimeError('Isolated Firefox did not connect; check Firefox and npm/web-ext installation' + ('\n'+details if details else '') + ('\nBootstrap diagnostics: '+json.dumps(diagnostics) if debug else ''))
                time.sleep(.1)
            client = MCPClient(origin,token,logs)
            initialized = client.rpc('initialize',{'protocolVersion':'2025-03-26'})
            yield client, initialized['serverInfo']['version']
        finally:
            if client:
                client.close()
            if runner and runner.poll() is None:
                os.killpg(runner.pid,signal.SIGTERM)
                try:
                    runner.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(runner.pid,signal.SIGKILL); runner.wait()
            cache = getattr(_http_connections,'cache',{})
            for connection,_ in cache.values():
                connection.close()
            cache.clear()
            broker.shutdown(); broker.server_close(); owner.join()


def viewport(value):
    try:
        width,height = map(int,value.lower().split('x'))
    except ValueError:
        raise argparse.ArgumentTypeError('Use WIDTHxHEIGHT, for example 1280x720') from None
    if not 320 <= width <= 3840 or not 320 <= height <= 2160:
        raise argparse.ArgumentTypeError('Width must be 320–3840 and height 320–2160')
    return width,height


def audit(client, urls, viewports, selectors, screenshot_directory=None, max_matches=3):
    pages = []
    for url in urls:
        opened,_ = client.command('open',{'url':url,'waitUntil':'complete'})
        tab = opened['id']; page = {'url':url,'viewports':[]}
        try:
            for width,height in viewports:
                measured,_ = client.command('viewport',{'tabId':tab,'width':width,'height':height})
                sample = {'requested':measured['requested'],'actual':measured['actual'],'matched':measured['matched'],'selectors':[]}
                if measured.get('nextStep'): sample['nextStep'] = measured['nextStep']
                for selector in selectors:
                    target = {'selector':selector}
                    try:
                        located,_ = client.command('locate',{'tabId':tab,'selector':selector,'maxElements':max_matches,'selectors':False},['elements'])
                        target.update(count=located['count'],returned=located['returned'],truncated=located['truncated'],elements=[])
                        for element in located['elements']:
                            inspected,_ = client.command('inspect',{'tabId':tab,'ref':element['ref'],'layout':True},['tag','role','rect','layout','visible','enabled'])
                            target['elements'].append({key:item for key,item in inspected.items() if key != 'ref'})
                    except AuditFailure as error:
                        target['error'] = {key:error.detail[key] for key in ('code','nextSteps','actionMayHaveOccurred') if key in error.detail}
                    sample['selectors'].append(target)
                if screenshot_directory:
                    metadata,images = client.command('screenshot',{'tabId':tab,'format':'png'})
                    destination = Path(screenshot_directory); destination.mkdir(parents=True,exist_ok=True,mode=0o700)
                    filename = destination/f'page-{len(pages)+1}-{width}x{height}.png'
                    descriptor = os.open(filename,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0),0o600)
                    os.fchmod(descriptor,0o600)
                    with os.fdopen(descriptor,'wb') as stream:
                        stream.write(base64.b64decode(images[metadata['imageIndex']]['data'],validate=True))
                    sample['screenshot'] = str(filename)
                page['viewports'].append(sample)
        finally:
            client.command('close',{'tabId':tab})
        pages.append(page)
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls',nargs='+',help='Explicit HTTP(S) page URLs to audit')
    parser.add_argument('--viewport',type=viewport,action='append',dest='viewports',help='Repeat e.g. 1280x720 and 390x844')
    parser.add_argument('--selector',action='append',help='CSS selector to inspect; repeat (default body)')
    parser.add_argument('--max-matches',type=int,default=3,help='Maximum elements inspected per selector (1–20)')
    parser.add_argument('--firefox',default='/usr/bin/firefox')
    parser.add_argument('--output',help='Optional private JSON report file')
    parser.add_argument('--debug-startup',action='store_true',help='Collect redacted startup stages in the private temporary test server')
    parser.add_argument('--screenshot-dir',help='Save PNG screenshots only when explicitly requested')
    args = parser.parse_args()
    if not 1 <= args.max_matches <= 20:
        parser.error('--max-matches must be 1–20')
    if len(args.viewports or []) > 8:
        parser.error('At most eight viewport sizes per page')
    for url in args.urls:
        if urlsplit(url).scheme not in {'http','https'} or not urlsplit(url).hostname:
            parser.error('Provide explicit HTTP(S) URLs')
    with isolated_firefox(args.firefox,args.debug_startup) as (client,version):
        report = {'browser':'isolated Firefox desktop','mcpVersion':version,'driver':'Browser Bridge MCP',
            'limitation':'Desktop responsive-layout evidence; does not verify Android rendering. Resizes only an isolated window.',
            'pages':audit(client,args.urls,args.viewports or [(1280,720),(390,844)],args.selector or ['body'],args.screenshot_dir,args.max_matches)}
    text = json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        target = Path(args.output); target.parent.mkdir(parents=True,exist_ok=True)
        descriptor,temporary = tempfile.mkstemp(prefix='.audit-',dir=target.parent)
        try:
            with os.fdopen(descriptor,'w') as stream:
                stream.write(text)
            os.replace(temporary,target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    print(text,end='')


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,OSError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
