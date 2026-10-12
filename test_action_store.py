import unittest,tempfile
from pathlib import Path
from action_store import ActionStore
class ActionStoreTests(unittest.TestCase):
 def test_restart_reconciles_without_secrets_or_replay(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'actions.sqlite';s=ActionStore(path);digest=s.fingerprint('d','fill',{'value':'private-marker'})
   s.reserve('client','a',digest,'command');s.update('command','dispatched');s.close()
   s=ActionStore(path);self.assertEqual(s.lookup('client','a',digest)['state'],'unknown')
   self.assertIsNone(s.lookup('other','a'))
   with self.assertRaisesRegex(ValueError,'ACTION_CONFLICT'):s.lookup('client','a','other')
   self.assertNotIn(b'private-marker',path.read_bytes());self.assertEqual(path.stat().st_mode&0o777,0o600);s.close()
 def test_capacity_does_not_evict_live_dedup_identity(self):
  s=ActionStore(limit=1);s.reserve('c','a','d','id')
  with self.assertRaisesRegex(ValueError,'ACTION_CAPACITY'):s.reserve('c','b','e','id2')
  self.assertEqual(s.lookup('c','a')['id'],'id');s.close()

 def test_two_brokers_cannot_reset_live_journal(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'actions.sqlite';one=ActionStore(path)
   try:
    one.reserve('client','action','digest','command')
    with self.assertRaises(RuntimeError):ActionStore(path)
    self.assertEqual(one.lookup('client','action')['state'],'queued')
   finally:one.close()

 def test_caller_action_identity_is_preserved_before_transmission(self):
  from bridge import run_command
  sent=[];args={'selector':'#button','actionId':'stable_action_identity_001'}
  def request(origin,token,path,payload):
   sent.append(payload);return {'state':'done','result':{'ok':True}}
  run_command('http://127.0.0.1','private','device','click',args,request=request)
  self.assertEqual(sent[0]['actionId'],args['actionId'])
  self.assertNotIn('actionId',sent[0]['args'])
  self.assertIn('actionId',args)
  with self.assertRaises(ValueError):run_command('http://127.0.0.1','private','device','click',args,action_id='different_action_identity',request=request)
  self.assertEqual(len(sent),1)

 def test_read_flood_preserves_mutation_capacity_and_explicit_dedup(self):
  import time
  from bridge import Broker, BrokerError, run_command
  b=Broker(action_limit=1);b.devices['device']=time.time()
  def request(origin,token,path,payload):
   accepted=b.handle('/api/command',payload)
   command=b.commands[accepted['id']]
   if command['state']!='done':
    b.handle('/api/poll',{'device':'device'})
    b.handle('/api/result',{'device':'device','id':accepted['id'],'result':{'ok':True}})
   return {'state':'done','result':{'ok':True}}
  for _ in range(40):run_command('local','private','device','read',{'tabId':1},request=request)
  self.assertEqual(b.action_store.stats()['count'],0)
  identity='stable_mutation_identity_001'
  run_command('local','private','device','click',{'tabId':1,'selector':'#x'},action_id=identity,request=request)
  self.assertEqual(b.action_store.stats()['count'],1)
  before=len(b.commands)
  run_command('local','private','device','click',{'tabId':1,'selector':'#x'},action_id=identity,request=request)
  self.assertEqual(len(b.commands),before)
  run_command('local','private','device','tabs',{},request=request)
  before=len(b.commands)
  with self.assertRaises(BrokerError) as caught:
   run_command('local','private','device','click',{'tabId':1,'selector':'#y'},request=request)
  self.assertEqual(caught.exception.code,'ACTION_CAPACITY')
  self.assertFalse(caught.exception.details['accepted'])
  self.assertGreater(caught.exception.details['retryAfterMs'],0)
  self.assertEqual(len(b.commands),before)
  b.action_store.close()

 def test_read_batch_and_explicit_read_identity(self):
  from bridge import run_command
  from action_store import needs_durable_identity
  self.assertFalse(needs_durable_identity('batch',{'steps':[{'op':'tabs'},{'op':'read','args':{'tabId':1}}]}))
  self.assertTrue(needs_durable_identity('batch',{'steps':[{'op':'read'},{'op':'click'}]}))
  self.assertTrue(needs_durable_identity('unknown'))
  sent=[]
  def request(origin,token,path,payload):
   sent.append(payload);return {'state':'done','result':{}}
  run_command('local','private','device','tabs',{},request=request)
  self.assertIsNone(sent[-1]['actionId'])
  run_command('local','private','device','tabs',{},action_id='explicit_read_identity_001',request=request)
  self.assertEqual(sent[-1]['actionId'],'explicit_read_identity_001')

 def test_client_quota_leaves_other_clients_capacity(self):
  from action_store import ActionCapacityError
  s=ActionStore(limit=3,client_limit=1);s.reserve('one','a','d','id')
  with self.assertRaises(ActionCapacityError) as caught:s.reserve('one','b','e','id2')
  self.assertEqual(caught.exception.details['scope'],'client')
  s.reserve('two','a','f','id3')
  self.assertEqual(s.stats('one')['clientCount'],1)
  self.assertEqual(s.lookup('one','a')['id'],'id')
  s.close()
