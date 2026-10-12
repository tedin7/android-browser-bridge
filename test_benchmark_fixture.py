import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from benchmark_fixture import make_server, private_json
from benchmark_hooks import run_hook, source_identity
from benchmark_setup import generate


class BenchmarkFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.server=make_server(0,'fixture-private-token');threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        private_json(self.root/'server.json',{'origin':self.origin,'token':'fixture-private-token'})
        repo=self.root/'repo';(repo/'extension').mkdir(parents=True)
        (repo/'mcp_server.py').write_text('# owned test source\n');(repo/'extension/manifest.json').write_text('{"version":"1.0.0"}')
        self.identity={'episodeId':'a'*20,'scenario':'form','revision':'candidate','client':'codex','buildId':source_identity(repo)}
        spec={'repo':str(repo),'buildId':self.identity['buildId'],'device':'fixture','expectedMcpVersion':'1.0.0','expectedExtensionVersion':'1.0.0'}
        self.config={'serverState':str(self.root/'server.json'),'browserOrigin':self.origin,'episodeDirectory':str(self.root/'episodes'),'revisions':{'candidate':spec,'baseline':spec}}
        self.tabs={};owner=self
        class FakeMCP:
            def __init__(self,spec):self.initial={'serverInfo':{'version':'1.0.0'}}
            def close(self):pass
            def command(self,device,op,args=None):
                args=args or {}
                if op=='capabilities':return {'version':'1.0.0'}
                if op=='open':
                    with urlopen(args['url']) as response:response.read()
                    tab=max(owner.tabs,default=0)+1;owner.tabs[tab]={'id':tab,'url':args['url'],'status':'complete'};return {'id':tab}
                if op=='tabs':return list(owner.tabs.values())
                if op=='close':owner.tabs.pop(args['tabId']);return {'ok':True}
                if op=='read':
                    tab=owner.tabs[args['tabId']];episode,slot=tab['url'].split('/')[-2:];e=owner.server.fixture_state.episodes[episode]
                    status={'form':'Saved '+e['expected'],'dynamic_filter':'Loaded 3 rows','concurrent_tabs':'Saved '+slot,'uncertain_result':'Verified action '+e['actionId']+': effect count 1'}[e['scenario']]
                    return {'text':status,'url':tab['url']}
                raise ValueError('Unexpected fake operation')
        self.client=FakeMCP

    def tearDown(self):self.server.shutdown();self.server.server_close();self.temp.cleanup()

    def post(self,path,data,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        with urlopen(Request(self.origin+path,data=json.dumps(data).encode(),headers=headers),timeout=3) as response:return json.load(response)

    def event(self,action,**values):
        return self.post('/event/'+self.identity['episodeId'],{'action':action,'slot':'main',**values})

    def test_real_lost_response_reconciled_without_second_effect(self):
        self.identity['scenario']='uncertain_result'
        prepared=run_hook(self.config,'prepare',self.identity,self.client)
        action=prepared['context']['actionId']
        with self.assertRaises((http.client.RemoteDisconnected,URLError)):
            self.event('commit',actionId=action)
        result=self.event('reconcile',actionId=action)
        self.assertEqual(result['effectCount'],1)
        verified=run_hook(self.config,'verify',self.identity,self.client)
        self.assertTrue(verified['verified']);self.assertTrue(verified['faultInjected']);self.assertEqual(verified['effectCount'],1)
        self.event('commit',actionId=action)
        self.assertFalse(run_hook(self.config,'verify',self.identity,self.client)['verified'])
        self.assertTrue(run_hook(self.config,'cleanup',self.identity,self.client)['cleaned']);self.assertFalse(self.tabs)

    def test_form_filter_and_two_tabs_independent_verification(self):
        for scenario in ('form','dynamic_filter','concurrent_tabs'):
            self.identity['scenario']=scenario
            prepared=run_hook(self.config,'prepare',self.identity,self.client)
            self.assertFalse(run_hook(self.config,'verify',self.identity,self.client)['verified'])
            if scenario=='form':self.event('form',value=prepared['context']['expectedValue'],choice='beta',consent=True)
            elif scenario=='dynamic_filter':self.event('filter',query='Beta')
            else:
                for slot in ('alpha','beta'):self.post('/event/'+self.identity['episodeId'],{'action':'tab','slot':slot,'value':slot})
            self.assertTrue(run_hook(self.config,'verify',self.identity,self.client)['verified'])
            run_hook(self.config,'cleanup',self.identity,self.client)

    def test_private_admin_boundary_and_source_drift(self):
        with self.assertRaises(HTTPError) as error:self.post('/admin/prepare',self.identity)
        self.assertEqual(error.exception.code,401)
        repo=Path(self.config['revisions']['candidate']['repo']);(repo/'mcp_server.py').write_text('# changed\n')
        with self.assertRaisesRegex(ValueError,'Frozen source changed'):run_hook(self.config,'prepare',self.identity,self.client)
        self.assertFalse(self.tabs)

    def test_cleanup_leaves_unrelated_tabs(self):
        run_hook(self.config,'prepare',self.identity,self.client)
        self.tabs[999]={'id':999,'url':'https://private.example/','status':'complete'}
        run_hook(self.config,'cleanup',self.identity,self.client)
        self.assertEqual(list(self.tabs),[999])

    def test_builtin_launchers_pin_only_selected_mcp_without_token_argv(self):
        from benchmark_agent import mcp_spec, agent_command
        spec=mcp_spec('/owned/revision','/private/profile.json')
        codex=agent_command('codex','/bin/codex','pinned',spec)
        self.assertIn('--ignore-user-config',codex)
        self.assertIn('--json',codex)
        self.assertEqual(codex[-1],'-')
        claude=agent_command('claude','/bin/claude','pinned',spec,'/private/config.json')
        self.assertIn('--strict-mcp-config',claude)
        self.assertIn('mcp__browser_bridge__*',claude)
        self.assertNotIn('--dangerously-skip-permissions',claude)

    def test_setup_generates_full_config_without_agents_or_credentials(self):
        profile=self.root/'connection.json';private_json(profile,{'url':'http://127.0.0.1:8766','token':'private-token-not-in-output'})
        repo=self.config['revisions']['candidate']['repo']
        settings={'serverState':str(self.root/'server.json'),'browserOrigin':self.origin,
                  'revisions':{r:{'repo':repo,'connectionFile':str(profile),'device':'fixture'} for r in ('baseline','candidate')},
                  'clients':{c:{'model':'frozen-model','settingsLabel':'frozen','command':['/owned/runner','--model','{model}','--repo','{repo}','--profile','{connectionFile}']} for c in ('codex','claude')}}
        result=generate(settings,self.root/'generated')
        self.assertFalse(result['agentsStarted']);self.assertEqual(result['episodes'],16)
        text=Path(result['gateConfig']).read_text();self.assertNotIn('private-token-not-in-output',text);self.assertNotIn('{repo}',text)
        config=json.loads(text);self.assertEqual(len(config['fixture']),3)
        self.assertEqual(Path(result['gateConfig']).stat().st_mode&0o777,0o600)


if __name__=='__main__':unittest.main()
