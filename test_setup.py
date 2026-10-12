"""Private connection profiles and dynamic one-command setup regressions."""
import contextlib
import io
import json
import os
import queue
import shutil
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from bridge import api, make_server
from test_attach import Client, close_http_connections

ROOT=Path(__file__).resolve().parent


class ProfileClient(Client):
    def __init__(self,profile,environment,auto=False):
        self.logs=tempfile.TemporaryFile(mode='w+')
        arguments=['--auto'] if auto else ['--connection-file',str(profile)]
        self.process=subprocess.Popen([sys.executable,str(ROOT/'android-browser-mcp.pyz'),*arguments],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.logs,text=True,env=environment)
        self.responses=queue.Queue();self.identifier=0
        def reader():
            try:
                for line in self.process.stdout:self.responses.put(json.loads(line))
            except Exception as error:self.responses.put(error)
            finally:self.responses.put(None)
        threading.Thread(target=reader,daemon=True).start()


class ProfileIntegrationTests(unittest.TestCase):
    def test_two_dynamic_profiles_attach_to_one_broker_without_client_state(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);token='profile-admin-fixture-'+'a'*30
            server=make_server(0,token);origin=f'http://127.0.0.1:{server.server_port}'
            owner=threading.Thread(target=server.serve_forever);owner.start()
            clients=[];jobs=[];stop=threading.Event();errors=[];browser=None
            try:
                code=api(origin,token,'/api/enroll',{'device':'fixture'})['code']
                browser_token=api(origin,'','/api/pair',{'code':code})['token']
                api(origin,browser_token,'/api/poll',{'device':'fixture'})
                def reply(command):
                    try:api(origin,browser_token,'/api/result',{'device':'fixture','id':command['id'],'result':{'tabId':command['args']['tabId']}})
                    except Exception as error:errors.append(error)
                    finally:close_http_connections()
                def poll():
                    try:
                        while not stop.is_set():
                            command=api(origin,browser_token,'/api/poll',{'device':'fixture','waitMs':100})['command']
                            if command:
                                job=threading.Thread(target=reply,args=(command,));jobs.append(job);job.start()
                    except Exception as error:errors.append(error)
                    finally:close_http_connections()
                browser=threading.Thread(target=poll);browser.start()
                for index,auto in enumerate([False,True]):
                    machine=base/f'different-machine-{index}';machine.mkdir()
                    profile=machine/'private arbitrary connection.json'
                    profile.write_text(json.dumps({'url':origin,'token':token,'browserUrl':origin,'device':'fixture'}));profile.chmod(0o600)
                    env=os.environ.copy()
                    for key in list(env):
                        if key.startswith('BROWSER_BRIDGE_'):env.pop(key)
                    env.update(BROWSER_BRIDGE_CONNECTION_FILE=str(profile),XDG_STATE_HOME=str(machine/'unused-local-state'))
                    client=ProfileClient(profile,env,auto);clients.append(client)
                    self.assertEqual(client.rpc('initialize',{'protocolVersion':'2025-03-26'})['serverInfo']['name'],'android-browser-bridge')
                identifiers=[client.send('tools/call',{'name':'browser_command','arguments':{'device':'fixture','op':'read','args':{'tabId':100+index}}}) for index,client in enumerate(clients)]
                for index,client in enumerate(clients):
                    result=client.receive();self.assertEqual(result['id'],identifiers[index]);self.assertFalse(result['result'].get('isError'))
                    self.assertEqual(json.loads(result['result']['content'][0]['text']),{'tabId':100+index})
                for client in clients:
                    client.logs.seek(0);self.assertFalse(token in client.logs.read(),'Credential emitted by attached client')
                for machine in base.glob('different-machine-*'):self.assertFalse((machine/'unused-local-state').exists())
                clients[0].close();clients.pop(0)
                self.assertFalse(clients[0].tool('read',{'tabId':200}).get('isError'))
                self.assertTrue(api(origin,token,'/api/devices',{})['devices']);self.assertFalse(errors)
            finally:
                for client in clients:client.close()
                stop.set()
                if browser:browser.join(timeout=2)
                for job in jobs:job.join(timeout=2)
                close_http_connections();server.shutdown();server.server_close();owner.join()


class ConnectionTests(unittest.TestCase):
    def test_private_profiles_follow_xdg_roots_and_dynamic_urls(self):
        from connection import connection_path,load_connection,save_connection
        with tempfile.TemporaryDirectory() as directory:
            for index,origin in enumerate(['http://127.0.0.1:19471','https://owned-linux.example:29481']):
                root=Path(directory)/f'root-{index}'
                with patch.dict(os.environ,{'XDG_STATE_HOME':str(root)},clear=True):
                    expected=connection_path()
                    profile={'url':origin,'token':'dummy-private-profile-token','browserUrl':origin,'device':'fixture'}
                    result=save_connection(profile)
                    self.assertEqual(Path(result),expected);self.assertEqual(expected.stat().st_mode&0o777,0o600)
                    loaded=load_connection();self.assertEqual(loaded['url'],origin);self.assertEqual(loaded['device'],'fixture')
                    self.assertEqual(loaded['token'],profile['token'])
                    self.assertTrue(expected.is_relative_to(root))
    def test_profile_modes_never_start_listener_or_emit_credentials(self):
        import launcher
        from connection import save_connection
        with tempfile.TemporaryDirectory() as directory:
            profile=Path(directory)/'private.json'
            save_connection({'url':'http://127.0.0.1:19479','token':'dummy-hidden-token'},profile)
            for arguments in [['--connection-file',str(profile)],['--auto']]:
                stdout=io.StringIO();stderr=io.StringIO()
                with self.subTest(mode=arguments[0]),patch.dict(os.environ,{'BROWSER_BRIDGE_CONNECTION_FILE':str(profile)},clear=True),patch.object(sys,'argv',['launcher.py',*arguments]),patch('launcher.make_server') as server,patch('launcher.token_file') as token,patch('launcher.mcp_main') as mcp,contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                    launcher.main();server.assert_not_called();token.assert_not_called();mcp.assert_called_once()
                    self.assertFalse('dummy-hidden-token' in stdout.getvalue()+stderr.getvalue(),'Credential emitted')
            profile.write_text('invalid JSON');profile.chmod(0o600)
            with patch.dict(os.environ,{'BROWSER_BRIDGE_CONNECTION_FILE':str(profile)},clear=True),patch.object(sys,'argv',['launcher.py','--auto']),patch('launcher.make_server') as server:
                with self.assertRaises(ValueError):launcher.main()
                server.assert_not_called()

    def test_missing_public_or_invalid_profile_never_creates_replacement(self):
        from connection import load_connection
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);missing=root/'missing.json'
            with self.assertRaises((ValueError,OSError)):load_connection(missing)
            self.assertFalse(missing.exists())
            profile=root/'public.json';profile.write_text(json.dumps({'url':'http://127.0.0.1:19471','token':'fixture-private-token'}));profile.chmod(0o644)
            with self.assertRaises(ValueError):load_connection(profile)
            profile.chmod(0o600)
            alias=root/'alias.json';alias.symlink_to(profile)
            with self.assertRaises(ValueError):load_connection(alias)
            profile.chmod(0o600);profile.write_text(json.dumps({'url':'javascript:bad','token':'fixture-private-token'}))
            with self.assertRaises(ValueError):load_connection(profile)


class InstallerTests(unittest.TestCase):
    def test_codex_discovers_legacy_connection_preserves_configs_and_helper_env(self):
        import install
        from connection import load_connection
        with tempfile.TemporaryDirectory() as directory:
            for index,origin in enumerate(['http://127.0.0.1:19581','https://linux-owned.example:29591']):
                home=Path(directory)/f'user-{index}';home.mkdir()
                state=home/'arbitrary private state';state.mkdir()
                token_path=state/'admin token';token_path.write_text('dummy-legacy-admin-token');token_path.chmod(0o600)
                codex_home=home/'.codex';codex_home.mkdir()
                codex_config=codex_home/'config.toml'
                original='model = "preserved-model"\n[mcp_servers.other]\ncommand = "preserved-other-command"\n'
                codex_config.write_text(original);codex_config.chmod(0o600)
                target=home/'.local/share/android-browser-bridge';target.mkdir(parents=True)
                existing={'setting':'preserve-top-level','mcpServers':{'other':{'command':'other','env':{'OTHER_PRIVATE':'dummy-unrelated-secret'}}}}
                config_path=target/'mcp-config.json';config_path.write_text(json.dumps(existing));config_path.chmod(0o600)
                old={'name':'android-browser','transport':{'type':'stdio','command':'python3','args':[str(ROOT/'mcp_server.py')],'env':{'BROWSER_BRIDGE_URL':origin,'BROWSER_BRIDGE_TOKEN_FILE':str(token_path),'BROWSER_BRIDGE_ANDROID_DEVICE':'fixture','BROWSER_BRIDGE_ANDROID_PACKAGE':'org.mozilla.fenix'}}}
                if index:
                    old['transport']['env'].pop('BROWSER_BRIDGE_TOKEN_FILE')
                    old['transport']['env']['BROWSER_BRIDGE_TOKEN']='dummy-legacy-admin-token'
                calls=[]
                def run(argv,**kwargs):
                    calls.append((argv,kwargs))
                    if 'mcp' in argv and ('list' in argv or 'get' in argv):return SimpleNamespace(returncode=0,stdout=json.dumps([old]),stderr='')
                    return SimpleNamespace(returncode=0,stdout='',stderr='')
                output=io.StringIO();error=io.StringIO()
                env={'CODEX_HOME':str(codex_home),'XDG_STATE_HOME':str(home/'selected state')}
                with patch.dict(os.environ,env,clear=True),patch('install.Path.home',return_value=home),patch.object(sys,'argv',['install.py','--codex']),patch('install.subprocess.run',side_effect=run),patch('install._probe_profile',return_value=True),patch.dict(sys.modules,{'agent_integration':SimpleNamespace(install_codex_guidance=lambda:{})}),patch('install.shutil.which',return_value='/usr/bin/fake-codex'),patch('builtins.input',side_effect=AssertionError('Dynamic setup must not prompt for an already configured connection')),contextlib.redirect_stdout(output),contextlib.redirect_stderr(error):
                    install.main()
                    profile=load_connection()
                self.assertEqual(profile['url'],origin);self.assertEqual(profile['token'],'dummy-legacy-admin-token')
                installed=json.loads(config_path.read_text());self.assertEqual(installed['setting'],existing['setting']);self.assertEqual(installed['mcpServers']['other'],existing['mcpServers']['other'])
                new=installed['mcpServers']['android-browser'];self.assertIn('--connection-file',new['args']);self.assertNotIn('--listen',new['args'])
                profile_path=Path(new['args'][new['args'].index('--connection-file')+1]);self.assertEqual(profile_path.stat().st_mode&0o777,0o600)
                add=[argv for argv,_ in calls if 'mcp' in argv and 'add' in argv];self.assertEqual(len(add),1)
                self.assertIn('BROWSER_BRIDGE_ANDROID_DEVICE=fixture',add[0]);self.assertIn('BROWSER_BRIDGE_ANDROID_PACKAGE=org.mozilla.fenix',add[0])
                self.assertFalse(any(kwargs.get('shell') for _,kwargs in calls))
                self.assertEqual(codex_config.read_text(),original)
                backups=[path for path in codex_home.rglob('*bak*') if path.is_file()]
                self.assertTrue(backups,'Existing Codex config needs a private backup');self.assertTrue(any(path.read_text()==original for path in backups))
                self.assertTrue(all(path.stat().st_mode&0o777==0o600 for path in backups))
                merge_backups=list(target.glob('mcp-config.json.bak-*'));self.assertTrue(merge_backups);self.assertEqual(json.loads(merge_backups[0].read_text()),existing)
                printed=output.getvalue()+error.getvalue()
                self.assertFalse('dummy-legacy-admin-token' in printed or 'dummy-unrelated-secret' in printed,'Raw credential emitted')

    def test_canonical_profile_wins_over_stale_bridge_and_occupied_unrelated_name(self):
        import install
        from connection import save_connection
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);codex_home=home/'.codex';codex_home.mkdir()
            (codex_home/'config.toml').write_text('model = "preserve"\n')
            target=home/'.local/share/android-browser-bridge';target.mkdir(parents=True)
            unrelated={'command':'different-tool','args':['keep-me']}
            config_path=target/'mcp-config.json';config_path.write_text(json.dumps({'mcpServers':{'android-browser':unrelated}}));config_path.chmod(0o600)
            occupied={'name':'android-browser','transport':{'type':'stdio',**unrelated}}
            stale={'name':'stale-bridge','transport':{'type':'stdio','command':'python3','args':[str(ROOT/'mcp_server.py')],'env':{'BROWSER_BRIDGE_URL':'http://127.0.0.1:19601','BROWSER_BRIDGE_TOKEN_FILE':str(home/'missing-token')}}}
            calls=[]
            def run(argv,**kwargs):
                calls.append(argv)
                return SimpleNamespace(returncode=0,stdout=json.dumps([occupied,stale]) if 'list' in argv else '',stderr='')
            env={'CODEX_HOME':str(codex_home),'XDG_STATE_HOME':str(home/'known state')}
            with patch.dict(os.environ,env,clear=True),patch('install.Path.home',return_value=home),patch.object(sys,'argv',['install.py','--codex']),patch('install.subprocess.run',side_effect=run),patch('install._probe_profile',return_value=True),patch.dict(sys.modules,{'agent_integration':SimpleNamespace(install_codex_guidance=lambda:{})}),patch('install.shutil.which',return_value='/usr/bin/fake-codex'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                save_connection({'url':'http://127.0.0.1:19611','token':'canonical-dummy-token'})
                install.main()
            configured=json.loads(config_path.read_text())['mcpServers']
            self.assertEqual(configured['android-browser'],unrelated);self.assertIn('android-browser-2',configured)
            add=next(argv for argv in calls if 'add' in argv)
            self.assertEqual(add[add.index('add')+1],'android-browser-2')
            self.assertIn('--connection-file',add);self.assertNotIn('--listen',add)


class GuidanceTests(unittest.TestCase):
    def test_managed_block_preserves_user_guidance_and_private_backups(self):
        import agent_integration
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);instructions=home/'AGENTS.md'
            before='Use my chosen provider and preserve unrelated settings.\n'
            after='\nNever alter my release workflow without explicit instructions.\n'
            original=before+agent_integration.START+'\nOld bridge routing\n'+agent_integration.END+after
            instructions.write_text(original);instructions.chmod(0o644)
            skill=home/'skills/android-browser-bridge/SKILL.md';skill.parent.mkdir(parents=True);skill.write_text('Previous bridge skill with local additions.\n')
            with patch.dict(os.environ,{'CODEX_HOME':str(home)},clear=True):
                result=agent_integration.install_codex_guidance()
                changed=instructions.read_text();self.assertTrue(changed.startswith(before));self.assertTrue(changed.endswith(after))
                self.assertEqual(changed.count(agent_integration.START),1);self.assertEqual(changed.count(agent_integration.END),1)
                self.assertNotIn('Old bridge routing',changed)
                source=ROOT/'agent-skills/android-browser-bridge/SKILL.md'
                self.assertEqual(skill.read_bytes(),source.read_bytes())
                backups=list(home.rglob('*.bak-*'));self.assertTrue(backups)
                self.assertTrue(any(path.read_text()==original for path in backups))
                self.assertTrue(any(path.read_text()=='Previous bridge skill with local additions.\n' for path in backups))
                self.assertTrue(all(path.stat().st_mode&0o777==0o600 for path in backups))
                self.assertEqual(instructions.stat().st_mode&0o777,0o600);self.assertEqual(skill.stat().st_mode&0o777,0o600)
                second=agent_integration.install_codex_guidance();self.assertFalse(second['updated'])
                self.assertEqual(set(home.rglob('*.bak-*')),set(backups));self.assertTrue(result['updated'])

    def test_existing_unmanaged_guidance_is_retained_and_incomplete_block_rejected(self):
        import agent_integration
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);instructions=home/'AGENTS.md';original='My unrelated assistant preferences.\n'
            instructions.write_text(original)
            with patch.dict(os.environ,{'CODEX_HOME':str(home)},clear=True):
                agent_integration.install_codex_guidance();self.assertTrue(instructions.read_text().startswith(original))
                broken='Preserve this custom text.\n'+agent_integration.START+'\nUnfinished user edit.\n'
                instructions.write_text(broken)
                with self.assertRaises(ValueError):agent_integration.install_codex_guidance()
                self.assertEqual(instructions.read_text(),broken)


class PersistentBootstrapTests(unittest.TestCase):
    @contextlib.contextmanager
    def isolated(self):
        import install
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/'app/android-browser-mcp.pyz';target.parent.mkdir();shutil.copy2(ROOT/'android-browser-mcp.pyz',target)
            state=root/'isolated-state';owners=[];original_popen=subprocess.Popen
            def launch(*args,**kwargs):
                process=original_popen(*args,**kwargs)
                if '--broker-only' in args[0]:owners.append(process)
                return process
            environment={key:value for key,value in os.environ.items() if not key.startswith('BROWSER_BRIDGE_')}
            environment['XDG_STATE_HOME']=str(state)
            with patch.dict(os.environ,environment,clear=True),patch('install.Path.home',return_value=root),patch('install.subprocess.Popen',side_effect=launch):
                try:yield install,target,SimpleNamespace(listen='127.0.0.1',port=None,url=None),owners,state
                finally:
                    for process in owners:
                        if process.poll() is None:
                            process.terminate()
                            try:process.wait(timeout=5)
                            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                    close_http_connections()

    def test_real_cold_daemon_dynamic_port_reuse_and_client_exit(self):
        from connection import load_connection
        from urllib.parse import urlsplit
        with self.isolated() as (install,target,args,owners,state):
            path=install.ensure_persistent_broker(target,args);profile=load_connection(path)
            self.assertGreater(urlsplit(profile['url']).port,0);self.assertEqual(len(owners),1)
            pid=(path.parent/'broker.pid').read_text()
            self.assertEqual(install.ensure_persistent_broker(target,args,path),path)
            self.assertEqual((path.parent/'broker.pid').read_text(),pid);self.assertEqual(len(owners),1)
            for name in ['broker.pid','broker.log','token','connection.json']:
                self.assertEqual((path.parent/name).stat().st_mode&0o777,0o600)
            client=ProfileClient(path,os.environ.copy())
            try:
                client.rpc('initialize',{'protocolVersion':'2025-03-26'})
                response=client.rpc('tools/call',{'name':'browser_devices','arguments':{}})
                self.assertFalse(response.get('isError'))
            finally:client.close()
            self.assertTrue(install._probe_profile(profile));self.assertIsNone(owners[0].poll())

    def test_custom_connection_filename_bootstraps_and_reuses_private_owner(self):
        from connection import load_connection
        with self.isolated() as (install,target,args,owners,state):
            selected=state/'custom private profile.json'
            with patch.dict(os.environ,{'BROWSER_BRIDGE_CONNECTION_FILE':str(selected)}):
                path=install.ensure_persistent_broker(target,args)
                self.assertEqual(path,selected.resolve())
                profile=load_connection(path)
                self.assertTrue(install._probe_profile(profile))
                self.assertEqual(path.stat().st_mode&0o777,0o600)
                self.assertEqual(profile,load_connection(selected.parent/'connection.json'))
                self.assertEqual(install.ensure_persistent_broker(target,args,path),path)
                self.assertEqual(len(owners),1)
                selected.unlink()
                self.assertEqual(install.ensure_persistent_broker(target,args),path)
                self.assertEqual(load_connection(path),profile)
                self.assertEqual(len(owners),1)
                owners[0].terminate();owners[0].wait(timeout=5)
                self.assertEqual(install.ensure_persistent_broker(target,args,path),path)
                self.assertEqual(load_connection(path),profile)
                self.assertEqual(len(owners),2)
                self.assertTrue(install._probe_profile(profile))
            self.assertFalse((state/'android-browser-bridge').exists())

    def test_two_concurrent_cold_installers_start_exactly_one_owner(self):
        from connection import load_connection
        with self.isolated() as (install,target,args,owners,state),ThreadPoolExecutor(max_workers=2) as pool:
            pending=[pool.submit(install.ensure_persistent_broker,target,args) for _ in range(2)]
            paths=[task.result(timeout=15) for task in pending]
            self.assertEqual(paths[0],paths[1]);self.assertEqual(len(owners),1)
            self.assertEqual(int((paths[0].parent/'broker.pid').read_text()),owners[0].pid)
            self.assertTrue(install._probe_profile(load_connection(paths[0])))

    def test_known_stopped_owner_restarts_without_changing_profile_or_token(self):
        from connection import load_connection
        with self.isolated() as (install,target,args,owners,state):
            path=install.ensure_persistent_broker(target,args);original=load_connection(path)
            owners[0].terminate();owners[0].wait(timeout=5)
            self.assertFalse(install._probe_profile(original))
            restarted=install.ensure_persistent_broker(target,args,path)
            self.assertEqual(restarted,path);self.assertEqual(load_connection(path),original)
            self.assertEqual(len(owners),2);self.assertNotEqual(owners[0].pid,owners[1].pid)
            self.assertTrue(install._probe_profile(original))


if __name__=='__main__':unittest.main()
