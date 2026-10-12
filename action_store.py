"""Private durable action identities; no page contents or input values are stored."""
import hashlib
import json
import os
import sqlite3
import time
import weakref
import fcntl
from pathlib import Path

def needs_durable_identity(operation, arguments=None):
    """Unknown or effectful operations are conservative; pure observations need no journal."""
    from operation_registry import REGISTRY
    if operation == 'batch':
        steps = (arguments or {}).get('steps')
        return not isinstance(steps, list) or any(
            not isinstance(step, dict) or needs_durable_identity(step.get('op'), step.get('args'))
            for step in steps)
    return REGISTRY['operations'].get(operation, {}).get('effect') not in {'observe', 'read'}


class ActionCapacityError(ValueError):
    def __init__(self, details):
        super().__init__('ACTION_CAPACITY: durable identity capacity reached; no action dispatched')
        self.details = details


class ActionStore:
    def __init__(self,path=None,ttl=86400,limit=10000,client_limit=None):
        if ttl <= 0 or limit < 1 or (client_limit is not None and client_limit < 1):
            raise ValueError('Invalid action journal limits')
        self.ttl,self.limit,self.client_limit=ttl,limit,client_limit
        owner_fd=None
        if path:
            path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
            owner_fd=os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            try:fcntl.flock(owner_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:
                os.close(owner_fd)
                raise RuntimeError('Action store is already owned by another broker') from None
            fd=os.open(path,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd);path.chmod(0o600)
        self.db=sqlite3.connect(str(path) if path else ':memory:',check_same_thread=False)
        def cleanup(db,fd):
            db.close()
            if fd is not None:os.close(fd)
        self._finalizer=weakref.finalize(self,cleanup,self.db,owner_fd)
        self.db.execute('CREATE TABLE IF NOT EXISTS actions (client TEXT, action TEXT, digest TEXT, command TEXT, state TEXT, created REAL, PRIMARY KEY(client,action))')
        self.db.execute("UPDATE actions SET state='unknown' WHERE state IN ('queued','dispatched')")
        self.db.commit()
    @staticmethod
    def fingerprint(device,operation,arguments):
        return hashlib.sha256(json.dumps([device,operation,arguments],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    def lookup(self,client,action,digest=None):
        row=self.db.execute('SELECT digest,command,state,created FROM actions WHERE client=? AND action=?',(client,action)).fetchone()
        if row is None:return None
        if row[3] + self.ttl <= time.time():
            self.db.execute('DELETE FROM actions WHERE client=? AND action=?',(client,action))
            self.db.commit()
            return None
        if digest is not None and row[0]!=digest:raise ValueError('ACTION_CONFLICT: actionId reused with a different payload')
        return {'id':row[1],'actionId':action,'state':row[2],'retainedUntil':row[3]+self.ttl}
    def reserve(self,client,action,digest,command):
        now=time.time()
        self.db.execute('DELETE FROM actions WHERE created<?',(now-self.ttl,))
        total = self.stats(client)
        per_client_full = self.client_limit is not None and total['clientCount'] >= self.client_limit
        if total['count'] >= self.limit or per_client_full:
            expiry = self.db.execute('SELECT MIN(created) FROM actions' + (' WHERE client=?' if per_client_full else ''), (client,) if per_client_full else ()).fetchone()[0] + self.ttl
            self.db.commit()
            raise ActionCapacityError({'accepted': False, 'actionMayHaveOccurred': False,
                'retainedUntil': expiry, 'retryAfterMs': max(1, int((expiry-now)*1000)+1),
                'scope': 'client' if per_client_full else 'global',
                'nextSteps': ['Wait until retainedUntil before resubmitting this same actionId, or increase the configured journal capacity.',
                              'Reads, status and revocation remain available; do not clear retained identities.']})
        self.db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?)',(client,action,digest,command,'queued',now));self.db.commit()
    def stats(self, client=None):
        now = time.time()
        count, oldest = self.db.execute('SELECT COUNT(*), MIN(created) FROM actions WHERE created>?', (now-self.ttl,)).fetchone()
        result = {'count': count, 'limit': self.limit, 'ttlSeconds': self.ttl,
                  'earliestExpiry': oldest+self.ttl if oldest is not None else None,
                  'clientLimit': self.client_limit}
        if client is not None:
            result['clientCount'] = self.db.execute('SELECT COUNT(*) FROM actions WHERE client=? AND created>?', (client,now-self.ttl)).fetchone()[0]
        return result
    def update(self,command,state):
        self.db.execute('UPDATE actions SET state=? WHERE command=?',(state,command));self.db.commit()
    def close(self):self._finalizer()
