#!/usr/bin/env python3
"""Freeze complete release-gate/hook configs from explicit local settings; no agents."""
import argparse
import json
import re
from pathlib import Path
import sys
from benchmark_fixture import private_json
from benchmark_hooks import source_identity
from connection import load_connection, validate_origin
from release_gate import validate_config


def generate(settings, output):
    output=Path(output).resolve();output.mkdir(mode=0o700,parents=True,exist_ok=True)
    hooks={'serverState':str(Path(settings['serverState']).resolve()),'browserOrigin':validate_origin(settings['browserOrigin']),
           'episodeDirectory':str(output/'episodes'),'revisions':{}}
    for revision in ('baseline','candidate'):
        item=settings['revisions'][revision]
        if not isinstance(item.get('device'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',item['device']):raise ValueError('Explicit authorized device ID required')
        repo=Path(item['repo']).resolve();profile=Path(item['connectionFile']).resolve()
        load_connection(profile) # Validate presence/privacy without copying its token.
        manifest=json.loads((repo/'extension/manifest.json').read_text())
        hooks['revisions'][revision]={'repo':str(repo),'connectionFile':str(profile),'device':item['device'],
                                     'buildId':source_identity(repo),'mcpCommand':[sys.executable,str(repo/'mcp_server.py')],
                                     'expectedMcpVersion':item.get('expectedMcpVersion',manifest['version']),
                                     'expectedExtensionVersion':manifest['version']}
    clients={}
    for client in ('codex','claude'):
        model=settings['clients'][client]
        template=model.get('command')
        if template is None:
            template=[sys.executable,str(Path(__file__).with_name('benchmark_agent.py').resolve()),'--client',client,'--model','{model}','--repo','{repo}','--connection','{connectionFile}']
            if model.get('executable'):template+=['--executable',model['executable']]
        if not isinstance(template,list) or not template:raise ValueError('Frozen client command argv required')
        clients[client]={'model':model['model'],'settingsLabel':model['settingsLabel']}
        for revision in ('baseline','candidate'):
            spec=hooks['revisions'][revision]
            work=output/(client+'-'+revision);work.mkdir(mode=0o700,exist_ok=True)
            replacements={'{repo}':spec['repo'],'{connectionFile}':spec['connectionFile'],'{device}':spec['device'],'{model}':model['model'],'{cwd}':str(work)}
            command=[]
            for argument in template:
                if not isinstance(argument,str):raise ValueError('Command arguments must be strings')
                for old,new in replacements.items():argument=argument.replace(old,new)
                command.append(argument)
            clients[client][revision]={'command':command,'cwd':str(work),'buildId':spec['buildId']}
    hook_path=output/'fixture-hooks.json'
    gate={'version':1,'clients':clients,'fixture':{action:[sys.executable,str(Path(__file__).with_name('benchmark_hooks.py').resolve()),str(hook_path),action] for action in ('prepare','verify','cleanup')}}
    validate_config(gate)
    private_json(hook_path,hooks);private_json(output/'release-gate.json',gate)
    return {'gateConfig':str(output/'release-gate.json'),'hookConfig':str(hook_path),'episodes':16,'agentsStarted':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('settings');parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    print(json.dumps(generate(json.loads(Path(args.settings).read_text()),args.output_dir)))


if __name__=='__main__':main()
