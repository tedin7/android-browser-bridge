import unittest
from step_runtime import execute_step


class StepTests(unittest.TestCase):
    def test_verified_form_returns_final_evidence_only(self):
        calls=[]
        def dispatch(op,args,timeout):
            calls.append((op,args,timeout))
            if op=='inspect': return {'value':'updated','privateExtra':'omit'}
            return {'ok':True,'privateExtra':'omit'}
        result=execute_step({'tabId':1,'steps':[{'op':'fill','args':{'selector':'#name','value':'updated'}},{'op':'click','args':{'selector':'#save'}}], 'verify':[{'kind':'value','args':{'selector':'#name'},'expected':'updated'}]},dispatch)
        self.assertEqual(result['state'],'verified')
        self.assertEqual(result['completed'],2)
        self.assertNotIn('privateExtra',str(result))
        self.assertEqual([c[0] for c in calls],['fill','click','inspect'])
        self.assertTrue(all(c[1]['tabId']==1 and 0<c[2]<=60000 for c in calls))

    def test_invalid_later_step_rejected_before_first_action(self):
        calls=[]
        invalid=[{'op':'evaluate','args':{}},{'op':'fill','args':{'selector':'#x','value':123}},{'op':'fill','args':{'value':{'$result':{'step':9,'path':['value']}}}}]
        for step in invalid:
            with self.assertRaises(ValueError):
                execute_step({'tabId':1,'steps':[{'op':'click','args':{'selector':'#save'}},step]},lambda *a:calls.append(a))
        self.assertEqual(calls,[])

    def test_failed_precondition_never_dispatches_mutation(self):
        calls=[]
        def dispatch(op,args,timeout): calls.append(op); return {'elements':[]}
        result=execute_step({'tabId':1,'preconditions':[{'kind':'presence','args':{'selector':'#ready'},'expected':True}], 'steps':[{'op':'click','args':{'selector':'#save'}}]},dispatch)
        self.assertEqual(result['state'],'precondition_failed')
        self.assertFalse(result['actionMayHaveOccurred'])
        self.assertEqual(calls,['locate'])

    def test_reference_resolved_and_final_output_explicit(self):
        calls=[]
        def dispatch(op,args,timeout):
            calls.append((op,args))
            return {'value':'reused','privateExtra':'omit'}
        result=execute_step({'tabId':1,'steps':[{'op':'inspect','args':{'selector':'#source'}},{'op':'fill','args':{'selector':'#dest','value':{'$result':{'step':0,'path':['value']}}}}], 'outputFields':['value']},dispatch)
        self.assertEqual(result['state'],'executed')
        self.assertEqual(calls[1][1]['value'],'reused')
        self.assertEqual(result['output'],{'value':'reused'})

    def test_uncertain_mutation_never_repeated_and_stops_next_step(self):
        calls=[]
        def dispatch(op,args,timeout):
            calls.append(op)
            raise TimeoutError('sensitive details must not escape')
        result=execute_step({'tabId':1,'steps':[{'op':'click','args':{'selector':'#save'}},{'op':'click','args':{'selector':'#other'}}]},dispatch)
        self.assertEqual(result['state'],'unknown')
        self.assertEqual(calls,['click'])
        self.assertTrue(result['actionMayHaveOccurred'])
        self.assertNotIn('sensitive',str(result))

    def test_verification_timeout_repeats_only_observation(self):
        now=[0]; calls=[]
        def dispatch(op,args,timeout): calls.append(op); return {'value':'pending'}
        def sleep(seconds): now[0]+=seconds
        result=execute_step({'tabId':1,'timeoutMs':250,'steps':[{'op':'click','args':{'selector':'#save'}}], 'verify':[{'kind':'value','args':{'selector':'#status'},'expected':'saved'}]},dispatch,clock=lambda:now[0],sleep=sleep)
        self.assertEqual(result['state'],'verification_failed')
        self.assertEqual(calls.count('click'),1)
        self.assertGreater(calls.count('inspect'),1)
        self.assertEqual(result['completed'],1)

    def test_output_is_bounded(self):
        result=execute_step({'tabId':1,'steps':[{'op':'read'}],'outputFields':['text']},lambda *args:{'text':'x'*20000})
        self.assertTrue(result['outputOmitted'])
        self.assertNotIn('output',result)


if __name__=='__main__': unittest.main()
