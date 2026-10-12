"""Compact MCP outputs preserve actionable controls and execution evidence."""
import base64
import copy
import json
import os
import unittest
from unittest.mock import patch

from response_policy import response_options, prepare_arguments, project_response, image_content


def fixture():
    element={"ref":"document-e1","tag":"button","role":"button","text":"Confirm","accessibleName":"Confirm",
        "name":"submit","selector":"body > main > section:nth-of-type(3) > button:nth-of-type(1)",
        "rect":{"x":20,"y":100,"width":180,"height":40},"enabled":True,"visible":True,"type":"submit"}
    return {"url":"https://fixture.example/","title":"Fixture","documentId":"document","readyState":"complete",
        "text":"Fixture page", "elements":[element],"viewport":{"width":900,"height":600,"visibility":"visible"},
        "scroll":{"x":0,"y":0,"maxY":3000},"elementCount":100,"nextOffset":20,"textLength":4000,"textTruncated":True}


class ResponsePolicyTests(unittest.TestCase):
    def test_lean_defaults_do_not_override_explicit_limits_or_mutate_arguments(self):
        self.assertEqual(prepare_arguments('read',{},'compact'),{'textLimit':2000,'maxElements':20,'selectors':False,'responseFields':['accessibleName','name','type','href','checked']})
        self.assertEqual(prepare_arguments('locate',{},'compact'),{'maxElements':20,'selectors':False,'responseFields':['accessibleName','name','type','href','checked']})
        explicit={'textLimit':0,'maxElements':500,'selectors':True,'tabId':12}
        original=copy.deepcopy(explicit)
        self.assertEqual(prepare_arguments('read',explicit,'compact'),{**explicit,'responseFields':['accessibleName','name','type','href','checked','selector']})
        self.assertEqual(explicit,original)
        self.assertEqual(prepare_arguments('read',{},'full'),{})
        self.assertEqual(prepare_arguments('inspect',{},'compact'),{})
        batch={'steps':[{'op':'read'},{'op':'locate','args':{'maxElements':100}},{'op':'open','args':{'url':'https://fixture.example'}}]}
        previous=copy.deepcopy(batch);prepared=prepare_arguments('batch',batch,'compact')
        self.assertEqual(batch,previous);self.assertEqual(prepared['steps'][0]['args']['textLimit'],2000)
        self.assertEqual(prepared['steps'][1]['args']['maxElements'],100);self.assertEqual(prepared['steps'][2],batch['steps'][2])
        self.assertEqual(prepare_arguments('batch',batch,'full'),batch)

    def test_compact_keeps_refs_false_states_and_all_document_evidence(self):
        raw=fixture();raw['elements'].append({**raw['elements'][0],'ref':'document-e2','enabled':False,'visible':False,'accessibleName':'Different name','href':'/next','checked':True})
        original=copy.deepcopy(raw);compact=project_response('read',raw,'compact')
        for key in ('url','title','documentId','readyState','viewport','scroll','elementCount','nextOffset','textLength','textTruncated'):
            self.assertEqual(compact[key],raw[key])
        first,second=compact['elements']
        self.assertEqual(first['ref'],'document-e1');self.assertNotIn('rect',first);self.assertNotIn('selector',first)
        self.assertEqual(first['accessibleName'],'Confirm');self.assertNotIn('text',first);self.assertNotIn('enabled',first)
        self.assertFalse(second['enabled']);self.assertFalse(second['visible']);self.assertEqual(second['accessibleName'],'Different name')
        self.assertEqual(second['href'],'/next');self.assertTrue(second['checked']);self.assertEqual(raw,original)
        explicit=project_response('read',raw,'compact',arguments={'selectors':True})
        self.assertEqual(explicit['elements'][0]['selector'],raw['elements'][0]['selector'])
        self.assertIs(project_response('read',raw,'full'),raw)
        self.assertEqual(project_response('inspect',raw['elements'][0],'compact'),raw['elements'][0])

    def test_locate_always_exposes_total_returned_and_truncation(self):
        raw={'count':100,'elements':[fixture()['elements'][0]]}
        compact=project_response('locate',raw,'compact')
        self.assertEqual((compact['count'],compact['returned'],compact['truncated']),(100,1,True))
        empty=project_response('locate',{'count':0,'elements':[]},'compact')
        self.assertEqual((empty['returned'],empty['truncated']),(0,False))
        mode,fields=response_options({'resultMode':'fields','resultFields':['elements']})
        projected=project_response('locate',raw,mode,fields)
        self.assertEqual(projected['count'],100);self.assertTrue(projected['truncated'])

    def test_fields_cannot_remove_safety_or_navigation_and_errors_stay_exact(self):
        raw={**fixture(),'timing':{'totalMs':10},'state':'done','actionMayHaveOccurred':False}
        mode,fields=response_options({'resultMode':'fields','resultFields':['text']})
        result=project_response('read',raw,mode,fields)
        self.assertEqual(result['text'],raw['text']);self.assertNotIn('elements',result)
        for key in ('documentId','readyState','url','viewport','scroll','elementCount','nextOffset','textLength','textTruncated','timing','state','actionMayHaveOccurred'):
            self.assertEqual(result[key],raw[key])
        error={'code':'PAGE_RESPONSE_TIMEOUT','message':'Page may still complete','commandId':'c1','actionMayHaveOccurred':True,'nextSteps':['Inspect browser_status']}
        self.assertIs(project_response('read',error,'compact'),error)
        batch={'completed':1,'results':[{'op':'read','result':fixture()}],'error':{'index':1,**error}}
        projected=project_response('batch',batch,mode,fields,{'steps':[{'op':'read'}]})
        self.assertEqual(projected['error'],batch['error']);self.assertEqual(projected['completed'],1)
        self.assertEqual(projected['results'][0]['result']['text'],'Fixture page')

    def test_compact_descriptor_limits_preserve_refs_and_leave_navigation_urls_exact(self):
        raw=fixture();long_url='https://fixture.example/'+('p'*1000)+'?query=complete'
        raw['url']=long_url;raw['elements'][0].update(name='n'*1000,href=long_url)
        compact=project_response('read',raw,'compact')
        element=compact['elements'][0]
        self.assertEqual(element['ref'],'document-e1')
        self.assertEqual(len(element['name']),512);self.assertTrue(element['nameTruncated'])
        self.assertEqual(len(element['href']),512);self.assertTrue(element['hrefTruncated'])
        self.assertEqual(compact['url'],long_url);self.assertIs(project_response('read',raw,'full'),raw)
        self.assertEqual(raw['elements'][0]['href'],long_url)
        mode,fields=response_options({'resultMode':'fields','resultFields':['elements']})
        self.assertTrue(project_response('read',raw,mode,fields)['elements'][0]['hrefTruncated'])

    def test_fields_filters_inspect_and_capabilities_but_keeps_preconditions(self):
        raw={**fixture()['elements'][0],'value':'private form value','enabled':False,'visible':False,'readOnly':True,'focused':True}
        mode,fields=response_options({'resultMode':'fields','resultFields':['rect']})
        projected=project_response('inspect',raw,mode,fields)
        self.assertEqual(projected['rect'],raw['rect']);self.assertEqual(projected['ref'],raw['ref'])
        self.assertFalse(projected['enabled']);self.assertFalse(projected['visible']);self.assertTrue(projected['readOnly'])
        self.assertNotIn('value',projected);self.assertNotIn('focused',projected)
        _,fields=response_options({'resultMode':'fields','resultFields':['value']})
        self.assertEqual(project_response('inspect',raw,mode,fields)['value'],raw['value'])
        self.assertEqual(project_response('inspect',raw,'compact'),raw)
        _,fields=response_options({'resultMode':'fields','resultFields':['operations']})
        projected=project_response('capabilities',{'operations':['read'],'nativeAndroidUI':False,'trustedEvents':False},mode,fields)
        self.assertEqual(projected,{'operations':['read'],'trustedEvents':False})
        frames=[{'frameId':2,'parentFrameId':0,'url':'https://fixture.example/frame?large=query','extra':'discard'}]
        self.assertEqual(project_response('frames',frames,mode,fields),[{'frameId':2,'parentFrameId':0,'url':'https://fixture.example/frame','urlQueryOmitted':True}])
        _,fields=response_options({'resultMode':'fields','resultFields':['title']})
        tabs=[{'id':3,'url':'https://fixture.example/?exact=yes','title':'Fixture','active':True,'status':'complete'}]
        self.assertEqual(project_response('tabs',tabs,mode,fields),[{'id':3,'url':'https://fixture.example/?exact=yes','title':'Fixture','status':'complete'}])

    def test_top_and_nested_screenshots_use_image_blocks_without_base64_text(self):
        data=base64.b64encode(b'fixture image bytes').decode()
        screenshot={'mimeType':'image/png','data':data,'tabId':12}
        raw={'completed':3,'results':[{'op':'screenshot','result':screenshot},{'op':'read','result':fixture()},
            {'op':'batch','result':{'completed':1,'results':[{'op':'screenshot','result':{**screenshot,'tabId':13}}]}}],
            'error':{'index':3,'actionMayHaveOccurred':True,'nextSteps':['Inspect state']}}
        original=copy.deepcopy(raw);images,metadata=image_content('batch',raw)
        self.assertEqual(len(images),2);self.assertEqual(images[0]['data'],data)
        self.assertEqual(metadata['results'][0]['result']['imageIndex'],0)
        self.assertEqual(metadata['results'][2]['result']['results'][0]['result']['imageIndex'],1)
        self.assertNotIn(data,json.dumps(metadata));self.assertEqual(raw,original);self.assertEqual(metadata['error'],raw['error'])
        images,metadata=image_content('screenshot',screenshot)
        self.assertEqual(metadata['imageIndex'],0);self.assertNotIn('data',metadata)
        for bad in ({'mimeType':'text/html','data':data},{'mimeType':'image/png','data':'invalid base64!'}):
            with self.assertRaises(ValueError):image_content('screenshot',bad)
        # Ordinary page data is not inferred to be a screenshot.
        self.assertEqual(image_content('inspect',{'data':data})[0],[])

    def test_compact_frames_drop_large_queries_but_full_and_page_urls_stay_exact(self):
        url='https://frames.example/path?tracking='+('x'*10000)+'#fragment'
        raw=[{'frameId':0,'parentFrameId':-1,'url':url},
            {'frameId':2,'parentFrameId':0,'url':'https://frames.example/'+('p'*1000)},
            {'frameId':3,'parentFrameId':0,'url':'about:blank'}]
        compact=project_response('frames',raw,'compact')
        self.assertEqual(compact[0],{'frameId':0,'parentFrameId':-1,'url':'https://frames.example/path','urlQueryOmitted':True})
        self.assertEqual(len(compact[1]['url']),512);self.assertTrue(compact[1]['urlTruncated'])
        self.assertEqual(compact[2],raw[2]);self.assertIs(project_response('frames',raw,'full'),raw)
        page={**fixture(),'url':url}
        self.assertEqual(project_response('read',page,'compact')['url'],url)
        batch={'completed':1,'results':[{'op':'frames','result':raw}]}
        self.assertEqual(project_response('batch',batch,'compact')['results'][0]['result'],compact)

    def test_projection_validation_happens_before_any_action(self):
        import mcp_server
        invalid=[{'resultMode':'unknown'},{'resultMode':'fields','resultFields':['notAResultField']},
            {'resultMode':'fields','resultFields':[]},{'resultMode':'compact','resultFields':['text']},
            {'unexpected':'value'},{'resultMode':'fields','resultFields':['data']}, {'args':[]}]
        with patch.dict(os.environ,{'BROWSER_BRIDGE_TOKEN':'fixture-private-token'}),patch('mcp_server.execute_browser_command') as execute:
            for options in invalid:
                message={'method':'tools/call','params':{'name':'browser_command','arguments':{'device':'fixture','op':'click','args':{},**options}}}
                result=mcp_server.handle(message);self.assertTrue(result['isError'])
                details=json.loads(result['content'][0]['text']);self.assertEqual(details['code'],'INVALID_ARGUMENT')
                self.assertFalse(details['actionMayHaveOccurred']);execute.assert_not_called()

    def test_old_extension_cannot_silently_claim_layout_and_batch_stops_before_click(self):
        import mcp_server
        with patch('mcp_server.run_command',return_value={'ref':'fixture-e1','rect':{'x':0,'y':0}}) as dispatch:
            with self.assertRaisesRegex(RuntimeError,'UNSUPPORTED_OPERATION'):
                mcp_server.execute_browser_command('http://127.0.0.1:8766','fixture-token','fixture','inspect',{'selector':'body','layout':True})
            dispatch.reset_mock()
            batch={'steps':[{'op':'inspect','args':{'selector':'body','layout':True}},{'op':'click','args':{'selector':'button'}}]}
            result=mcp_server.execute_browser_command('http://127.0.0.1:8766','fixture-token','fixture','batch',batch)
            self.assertEqual(result['completed'],0);self.assertEqual(result['error']['code'],'UNSUPPORTED_OPERATION')
            self.assertEqual(result['error']['index'],0);self.assertEqual(dispatch.call_count,1)
            self.assertEqual(dispatch.call_args.args[3],'inspect')
        _,fields=response_options({'resultMode':'fields','resultFields':['layout']})
        value={'ref':'fixture-e1','layout':{'display':'grid'},'value':'omit'}
        self.assertEqual(project_response('inspect',value,'fields',fields),{'ref':'fixture-e1','layout':{'display':'grid'}})

    def test_mcp_boundary_defaults_and_batch_images_remain_compatible(self):
        import mcp_server
        message={'method':'tools/call','params':{'name':'browser_command','arguments':{'device':'fixture','op':'read','args':{'tabId':12}}}}
        with patch.dict(os.environ,{'BROWSER_BRIDGE_TOKEN':'fixture-private-token'}),patch('mcp_server.execute_browser_command',return_value=fixture()) as execute:
            result=mcp_server.handle(message)
            self.assertEqual(execute.call_args.args[-1],{'tabId':12,'textLimit':2000,'maxElements':20,'selectors':False,'responseFields':['accessibleName','name','type','href','checked']})
            self.assertNotIn('rect',json.loads(result['content'][0]['text'])['elements'][0])
            message['params']['arguments']['resultMode']='full';result=mcp_server.handle(message)
            self.assertEqual(execute.call_args.args[-1],{'tabId':12})
            self.assertEqual(json.loads(result['content'][0]['text']),fixture())
        data=base64.b64encode(b'fixture image bytes').decode()
        message['params']['arguments']={'device':'fixture','op':'batch','args':{'steps':[{'op':'screenshot'}]}}
        raw={'completed':1,'results':[{'op':'screenshot','result':{'mimeType':'image/jpeg','data':data,'tabId':12}}]}
        with patch.dict(os.environ,{'BROWSER_BRIDGE_TOKEN':'fixture-private-token'}),patch('mcp_server.execute_browser_command',return_value=raw):
            result=mcp_server.handle(message)
        self.assertEqual(result['content'][0]['type'],'image');self.assertNotIn(data,result['content'][1]['text'])
        self.assertEqual(json.loads(result['content'][1]['text'])['results'][0]['result']['imageIndex'],0)


if __name__=='__main__': unittest.main()
