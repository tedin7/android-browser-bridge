"""Recovery formatting and control-plane liveness regressions."""
import base64
import copy
import json
import os
import threading
import unittest
from unittest.mock import patch
import mcp_server


def message(name, **arguments):
    return {'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}


def text(result):
    return json.loads(next(block['text'] for block in result['content'] if block['type'] == 'text'))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BROWSER_BRIDGE_TOKEN': 'test-token'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_status_and_immediate_have_identical_projected_results(self):
        raw = {'elements': [{'ref':'d-e1','rect':{'x':1},'accessibleName':'Submit','text':'Submit','visible':True}], 'documentId':'d', 'text':'sample'}
        receipt = {'id':'c1', 'state':'done', 'operation':'read', 'responseArgs':{}, 'result':raw, 'timing':{'totalMs':2}}
        original = copy.deepcopy(receipt)
        for options in ({}, {'resultMode':'full'}, {'resultMode':'fields','resultFields':['text']}):
            with patch('mcp_server.execute_browser_command', return_value=raw):
                direct = mcp_server.handle(message('browser_command', device='test',op='read',**options))
            with patch('mcp_server.broker_api', return_value=receipt):
                recovered = mcp_server.handle(message('browser_status',id='c1',**options))
            value = text(recovered)
            self.assertEqual(value['result'],text(direct))
            self.assertEqual(value['timing'],receipt['timing'])
            self.assertNotIn('responseArgs',value)
        self.assertEqual(receipt,original)

    def test_recovered_batch_screenshot_is_not_text_base64(self):
        data=base64.b64encode(b'test-only-image').decode()
        receipt={'id':'c2','state':'done','operation':'batch','responseArgs':{'steps':[{'op':'screenshot','args':{}}]},'result':{'completed':1,'results':[{'op':'screenshot','result':{'mimeType':'image/png','data':data}}]}}
        with patch('mcp_server.broker_api',return_value=receipt):
            result=mcp_server.handle(message('browser_status',id='c2'))
        self.assertEqual(result['content'][0]['data'],data)
        self.assertNotIn(data,result['content'][1]['text'])
        self.assertEqual(text(result)['result']['results'][0]['result']['imageIndex'],0)

    def test_status_validation_precedes_broker_call(self):
        with patch('mcp_server.broker_api') as broker:
            result=mcp_server.handle(message('browser_status',id='c1',resultMode='fields',resultFields=['data']))
        self.assertTrue(result['isError'])
        broker.assert_not_called()

    def test_old_broker_metadata_missing_fails_without_exposing_raw_payload(self):
        with patch('mcp_server.broker_api',return_value={'id':'c1','state':'done','result':{'data':'sensitive-image'}}):
            result=mcp_server.handle(message('browser_status',id='c1'))
        self.assertNotIn('sensitive-image',json.dumps(result))
        self.assertEqual(text(result)['error']['code'],'RESULT_METADATA_UNAVAILABLE')
        self.assertEqual(text(result)['id'],'c1')

    def test_error_and_pending_receipts_preserved_without_policy_metadata(self):
        for receipt in ({'id':'c1','state':'dispatched'}, {'id':'c1','state':'expired','error':'deadline','timing':{'queueMs':9}}):
            with patch('mcp_server.broker_api',return_value={**receipt,'responseArgs':{}}):
                result=mcp_server.handle(message('browser_status',id='c1'))
            self.assertEqual(text(result),receipt)

    def test_control_requests_pass_four_blocked_actions_and_two_status_waits(self):
        release=threading.Event()
        ready=threading.Barrier(7)
        controlled=threading.Event()
        rejected=[]
        def respond(request):
            if mcp_server.request_lane(request) in {'action','wait'}:
                ready.wait(timeout=3)
                release.wait(timeout=3)
            else:
                controlled.set()
        scheduler=mcp_server.RequestScheduler(respond,rejected.append)
        try:
            for _ in range(4): scheduler.submit(message('browser_command'))
            for _ in range(2): scheduler.submit(message('browser_status',waitMs=40000))
            ready.wait(timeout=3)
            scheduler.submit(message('browser_revoke',device='test'))
            self.assertTrue(controlled.wait(timeout=1),'revocation waited behind browser actions')
            controlled.clear()
            scheduler.submit(message('browser_status',waitMs=0))
            self.assertTrue(controlled.wait(timeout=1),'quick status waited behind long status requests')
            self.assertEqual(rejected,[])
        finally:
            release.set()
            scheduler.close()

    def test_lane_backlog_is_bounded_before_dispatch(self):
        release=threading.Event()
        invoked=[]
        rejected=[]
        def respond(request):
            release.wait(timeout=3)
            invoked.append(request)
        scheduler=mcp_server.RequestScheduler(respond,rejected.append)
        try:
            for i in range(64): self.assertTrue(scheduler.submit(message('browser_command',n=i)))
            last=message('browser_command',n=65)
            self.assertFalse(scheduler.submit(last))
            self.assertEqual(rejected,[last])
            self.assertEqual(invoked,[])
        finally:
            release.set()
            scheduler.close()
        self.assertEqual(len(invoked),64)

    def test_malformed_envelopes_reach_validation_without_crashing_router(self):
        malformed = [None, [], {'method':'tools/call','params':None},
                     {'method':'tools/call','params':[]},
                     {'method':'tools/call','params':{'name':[]}},
                     {'method':'tools/call','params':{'name':'browser_status','arguments':None}},
                     {'method':'tools/call','params':{'name':'browser_command','arguments':[]}}]
        for request in malformed:
            self.assertEqual(mcp_server.request_lane(request),'control')
        self.assertEqual(mcp_server.request_lane(message('browser_status',waitMs=1)),'wait')
        self.assertEqual(mcp_server.request_lane(message('browser_command')),'action')

    def test_step_transport_bounds_include_acquisition_and_independent_cleanup(self):
        now=[10.0]; calls=[]
        def api(url,token,path,payload,timeout):
            op=payload['op']; calls.append((op,timeout,payload['waitMs']))
            if op=='acquire_lease':
                now[0]+=.1
                value={'leaseGeneration':'fixture-generation'}
            elif op=='fill':
                # Response arrives after the workflow deadline. Do not proceed
                # to the next action, even though this response says done.
                now[0]+=.7
                value={'ok':True}
            else:
                value={'ok':True}
            return {'id':'fixture-command-1234','state':'done','result':value}
        plan={'tabId':7,'timeoutMs':500,'steps':[{'op':'fill','args':{'selector':'#field','value':'test'}},
                                               {'op':'click','args':{'selector':'#submit'}}]}
        with patch('mcp_server.LOCAL_BROKER',None),patch('mcp_server.api',side_effect=api),patch('mcp_server.time.monotonic',side_effect=lambda:now[0]):
            result=mcp_server.run_step('http://127.0.0.1:8766','test-token','test',plan)
        self.assertEqual(result['state'],'unknown')
        self.assertEqual([call[0] for call in calls],['acquire_lease','fill','release_lease'])
        self.assertLessEqual(calls[0][1],.5)
        self.assertLessEqual(calls[1][1],.401)
        self.assertAlmostEqual(calls[2][1],2.0)
        for _,timeout,wait_ms in calls:
            self.assertLessEqual(wait_ms,int(timeout*1000))

    def test_acquisition_time_is_removed_from_step_budget(self):
        now=[10.0]; executed=[]
        def api(url,token,path,payload,timeout):
            if payload['op']=='acquire_lease':
                self.assertLessEqual(timeout,10)
                now[0]+=.75
                value={'leaseGeneration':'fixture-generation'}
            else:
                self.assertLessEqual(timeout,2)
                raise OSError('cleanup transport failure')
            return {'id':'fixture-command-1234','state':'done','result':value}
        def execute(plan,dispatch):
            executed.append(plan['timeoutMs'])
            return {'state':'executed','verified':False}
        plan={'tabId':7,'timeoutMs':1500,'steps':[{'op':'read'}]}
        with patch('mcp_server.LOCAL_BROKER',None),patch('mcp_server.api',side_effect=api),patch('mcp_server.execute_step',side_effect=execute),patch('mcp_server.time.monotonic',side_effect=lambda:now[0]):
            result=mcp_server.run_step('http://127.0.0.1:8766','test-token','test',plan)
        self.assertEqual(executed,[750])
        self.assertEqual(result['state'],'executed')


if __name__=='__main__': unittest.main()
