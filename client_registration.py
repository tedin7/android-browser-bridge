"""Opt-in per-agent scoped profiles, keeping the owner's pairing credential private."""
from pathlib import Path
from bridge import api
from connection import load_connection, save_connection

def scoped_profile(owner_path,label):
    if label not in {'codex','claude'}:raise ValueError('Unsupported client label')
    owner=load_connection(owner_path)
    target=Path(owner_path).parent/('client-'+label+'.json')
    devices=api(owner['url'],owner['token'],'/api/devices',{})['devices']
    allowed=sorted(item['id'] for item in devices)
    if not allowed:raise ValueError('Pair a browser before creating scoped clients')
    if target.exists():
        saved=load_connection(target)
        if saved['url']==owner['url']:
            try:
                current=api(saved['url'],saved['token'],'/api/devices',{})['devices']
                # Installation must not silently expand an existing client's authority.
                if current and saved['token']!=owner['token'] and {item['id'] for item in current}.issubset(allowed):return target.resolve()
            except RuntimeError:
                pass # revoked profile is replaced only through the owner credential
    registered=api(owner['url'],owner['token'],'/api/clients/register',{'devices':allowed})
    profile={**owner,'token':registered['token']}
    try:return save_connection(profile,target).resolve()
    except Exception:
        try:api(owner['url'],owner['token'],'/api/clients/revoke',{'clientId':registered['clientId']})
        except Exception:pass
        raise
