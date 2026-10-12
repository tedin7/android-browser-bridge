import tempfile,unittest
from pathlib import Path
from native_artifacts import NativeArtifacts
class ShareTests(unittest.TestCase):
 def test_idempotent_private_bounded_origin_scoped_artifacts(self):
  with tempfile.TemporaryDirectory() as directory:
   s=NativeArtifacts(directory,max_bytes=20,max_total=40);body={'shareId':'a'*20,'text':'hello','name':'../../evil'}
   first=s.save('tablet',body);self.assertEqual(first,s.save('tablet',body))
   self.assertNotEqual(first['artifactId'],s.save('other',body)['artifactId'])
   self.assertEqual((Path(directory)/(first['artifactId']+'.bin')).stat().st_mode&0o777,0o600)
   with self.assertRaises(ValueError):s.save('tablet',{**body,'text':'changed'})
   with self.assertRaises(ValueError):s.save('tablet',{'shareId':'b'*20,'text':'x'*21})

class NativeRetrievalTests(unittest.TestCase):
 def test_ttl_ownership_and_missing_legacy_metadata(self):
  with tempfile.TemporaryDirectory() as directory:
   now=[100.0];store=NativeArtifacts(directory,ttl_seconds=10,clock=lambda:now[0])
   saved=store.save('tablet',{'shareId':'x'*20,'text':'private-fixture'})
   result=store.get(saved['artifactId'],'tablet',['tablet'])
   self.assertEqual(result['size'],len('private-fixture'))
   self.assertEqual((Path(directory)/(saved['artifactId']+'.json')).stat().st_mode&0o777,0o600)
   with self.assertRaises(PermissionError):store.get(saved['artifactId'],'tablet',['other'])
   with self.assertRaises(PermissionError):store.get(saved['artifactId'],'other',['other'])
   with self.assertRaises(ValueError):store.get('../../file','tablet')
   metadata=Path(directory)/(saved['artifactId']+'.json')
   metadata.unlink()
   with self.assertRaises(KeyError):store.get(saved['artifactId'],'tablet')
   with self.assertRaises(ValueError):store.save('tablet',{'shareId':'x'*20,'text':'private-fixture'})
   fresh=store.save('tablet',{'shareId':'z'*20,'text':'expiring'})
   now[0]+=11
   with self.assertRaises(KeyError):store.get(fresh['artifactId'],'tablet')
   self.assertFalse((Path(directory)/(fresh['artifactId']+'.bin')).exists())

 def test_native_retrieval_http_enforces_real_device_scope(self):
  import json,threading
  from urllib.request import Request,urlopen
  from urllib.error import HTTPError
  from bridge import make_server
  server=make_server(0,'fixture-admin-token')
  server.broker.credentials['tablet']='fixture-device-token'
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  origin='http://127.0.0.1:'+str(server.server_port)
  def request(path,data,token):
   req=Request(origin+path,data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
   try:
    with urlopen(req,timeout=3) as response:return response.status,json.load(response)
   except HTTPError as response:return response.code,json.load(response)
  try:
   status,saved=request('/api/native-share',{'device':'tablet','shareId':'a'*20,'text':'fixture'},'fixture-device-token');self.assertEqual(status,200)
   owner=server.broker.clients.register(['tablet']);other=server.broker.clients.register(['other'])
   data={'device':'tablet','artifactId':saved['artifactId']}
   self.assertEqual(request('/api/native-artifacts/get',data,owner['token'])[0],200)
   self.assertEqual(request('/api/native-artifacts/get',{**data,'_devices':['tablet']},other['token'])[0],403)
   self.assertEqual(request('/api/native-artifacts/get',{**data,'device':'other'},other['token'])[0],403)
   self.assertEqual(request('/api/native-artifacts/get',data,'fixture-admin-token')[0],200)
   self.assertEqual(request('/api/native-artifacts/get',data,'fixture-device-token')[0],401)
  finally:
   server.shutdown();server.server_close();thread.join();server.broker.action_store.close()
   if server.broker._artifact_temporary:server.broker._artifact_temporary.cleanup()
