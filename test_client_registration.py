import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from connection import save_connection,load_connection
from client_registration import scoped_profile
class RegistrationTests(unittest.TestCase):
 def test_owner_preserved_and_client_tokens_distinct(self):
  with tempfile.TemporaryDirectory() as directory:
   owner=Path(directory)/'connection.json';save_connection({'url':'http://127.0.0.1:9999','token':'owner-token'},owner)
   counter=[0]
   def request(url,token,path,data):
    if path=='/api/devices':return {'devices':[{'id':'tablet'}]}
    counter[0]+=1;return {'token':'client-token-'+str(counter[0]),'clientId':'client_'+str(counter[0])}
   with patch('client_registration.api',side_effect=request):
    one=scoped_profile(owner,'codex');two=scoped_profile(owner,'claude')
    self.assertEqual(one,scoped_profile(owner,'codex'))
   self.assertNotEqual(load_connection(one)['token'],load_connection(two)['token'])
   self.assertEqual(load_connection(owner)['token'],'owner-token');self.assertEqual(counter[0],2)

 def test_newly_paired_devices_do_not_silently_expand_existing_scope(self):
  with tempfile.TemporaryDirectory() as directory:
   owner=Path(directory)/'connection.json';save_connection({'url':'http://127.0.0.1:9999','token':'owner'},owner)
   existing=Path(directory)/'client-codex.json';save_connection({'url':'http://127.0.0.1:9999','token':'scoped'},existing)
   def request(url,token,path,data):
    self.assertEqual(path,'/api/devices')
    return {'devices':[{'id':'browser'},{'id':'native'}] if token=='owner' else [{'id':'browser'}]}
   with patch('client_registration.api',side_effect=request):self.assertEqual(scoped_profile(owner,'codex'),existing)
   self.assertEqual(load_connection(existing)['token'],'scoped')
