#!/usr/bin/env python3
"""Pinned Codex/Claude benchmark launcher, or private-profile MCP subprocess.

Only invoked for a paid episode by release_gate --run; setup never starts it.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from connection import load_connection


def mcp_spec(repo,connection):
    return {'command':sys.executable,'args':[str(Path(__file__).resolve()),'--mcp','--repo',str(Path(repo).resolve()),'--connection',str(Path(connection).resolve())]}


def agent_command(client, executable, model, spec, claude_config=None):
    if client=='codex':
        toml='{browser_bridge={command='+json.dumps(spec['command'])+',args='+json.dumps(spec['args'])+'}}'
        return [executable,'exec','--json','--model',model,'--sandbox','read-only','--skip-git-repo-check','--ephemeral','--ignore-user-config','-c','mcp_servers='+toml,'-']
    if client=='claude':
        return [executable,'--print','--verbose','--output-format','stream-json','--model',model,'--strict-mcp-config','--mcp-config',claude_config,'--tools','','--allowedTools','mcp__browser_bridge__*']
    raise ValueError('Unknown model client')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp',action='store_true');parser.add_argument('--client',choices=['codex','claude'])
    parser.add_argument('--executable');parser.add_argument('--model');parser.add_argument('--repo',required=True);parser.add_argument('--connection',required=True)
    args=parser.parse_args();repo=Path(args.repo).resolve()
    if not (repo/'mcp_server.py').is_file():parser.error('Browser Bridge checkout required')
    if args.mcp:
        profile=load_connection(args.connection)
        environment={**os.environ,'BROWSER_BRIDGE_URL':profile['url'],'BROWSER_BRIDGE_TOKEN':profile['token']}
        os.chdir(repo);os.execvpe(sys.executable,[sys.executable,str(repo/'mcp_server.py')],environment)
    if not args.client or not args.model:parser.error('Explicit client and pinned model required')
    spec=mcp_spec(repo,args.connection)
    with tempfile.TemporaryDirectory(prefix='browser-benchmark-client-') as directory:
        config=Path(directory)/'mcp.json'
        descriptor=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as stream:json.dump({'mcpServers':{'browser_bridge':spec}},stream)
        command=agent_command(args.client,args.executable or args.client,args.model,spec,str(config))
        return subprocess.run(command).returncode


if __name__=='__main__':raise SystemExit(main())
