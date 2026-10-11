"""Portable browser interaction checks; uses only our local, disposable fixture."""

def run_suite(operation, fixture_url, concurrent=None):
    pages=[]
    def open_page(suffix=''):
        tab=operation('open',{'url':fixture_url+suffix,'waitUntil':'complete'})['id'];pages.append(tab);return tab
    try:
        tab=open_page()
        def op(action,**args): return operation(action,{'tabId':tab,**args})
        def inspect(selector): return op('inspect',selector=selector)
        def text(selector): return op('read',selector=selector)['text']
        def rejects(action,code,**args):
            try: op(action,**args)
            except RuntimeError as error: assert code in str(error),(action,str(error))
            else: raise AssertionError(action+' unexpectedly succeeded')
        assert 'interaction lab' in op('read')['text']
        assert operation('capabilities')['trustedEvents'] is False
        op('click',selector='#click');assert text('#click-status')=='clicks:1'
        op('double_click',selector='#double');assert 'double clicked' in text('#double')
        op('hover',selector='#hover');assert text('#hover-status')=='hover:yes'
        for selector,code in [('#disabled','DISABLED'),('#hidden','NOT_VISIBLE'),('.duplicate','NOT_UNIQUE'),('#covered','COVERED')]: rejects('click',code,selector=selector)
        rejects('fill','READ_ONLY',selector='#readonly',value='x')
        rejects('fill','DISABLED',selector='#disabled-input',value='x')
        op('fill',selector='#text',value='quotes \' unicode à');assert inspect('#text')['value']=="quotes ' unicode à"
        op('clear',selector='#text');assert inspect('#text')['value']==''
        op('type',selector='#text',value='abcd');op('press',selector='#text',key='Control+A');op('press',selector='#text',key='Backspace');assert inspect('#text')['value']==''
        op('type',selector='#text',value='old');op('press',selector='#text',key='Control+A');op('type',selector='#text',value='replacement');assert inspect('#text')['value']=='replacement'
        op('focus',selector='#text');assert inspect('#text')['focused']
        op('fill',selector='#textarea',value='line1');op('press',selector='#textarea',key='Enter');assert inspect('#textarea')['value']=='line1\n'
        op('fill',selector='#editable',value='edited');assert inspect('#editable')['value']=='edited'
        op('fill',selector='#password',value='fixture-secret');assert 'value' not in inspect('#password')
        assert op('select',selector='#select',value='b')['values']==['b']
        assert op('select',selector='#multiple',values=['a','b'])['values']==['a','b']
        assert op('check',selector='#checkbox',checked=True)['checked'];assert not op('check',selector='#checkbox',checked=False)['checked']
        op('check',selector='#radio-one');op('check',selector='#radio-two');assert inspect('#radio-two')['checked'] and not inspect('#radio-one')['checked']
        op('press',selector='#text',key='Enter');assert text('#form-status')=='form:submitted'
        ref=op('locate',selector='#rerender')['elements'][0]['ref'];op('click',selector='#replace');rejects('inspect','STALE_REFERENCE',ref=ref)
        op('click',selector='#create-later');op('wait',selector='#delayed',timeoutMs=2000);op('click',selector='#remove-later');op('wait',selector='#delayed',state='detached',timeoutMs=1000)
        op('click',selector='#shadow-host >>> #shadow-button');assert text('#shadow-host >>> #shadow-result')=='shadow:clicked'
        op('fill',selector='#shadow-host >>> #shadow-input',value='shadow value');assert inspect('#shadow-host >>> #shadow-input')['value']=='shadow value'
        op('scroll',selector='#point-target',mode='intoView')
        rect=op('inspect',selector='#point-target')['rect'];x=round(rect['x']+20);y=round(rect['y']+20)
        rejects('click_point','INVALID_ARGUMENT',x=-1,y=0)
        op('click_point',x=x,y=y);assert text('#point-status')==f'point:{x},{y}'
        op('drag',x=x,y=y,toX=x+80,toY=y+30,dragSteps=8);assert text('#drag-status')==f'drag:{x+80},{y+30}'
        nested=op('scroll',selector='#nested',x=100,y=200);assert nested['after']['x']==100 and nested['after']['y']==200
        before=op('scroll',mode='absolute',x=0,y=0)['after'];after=op('scroll',x=0,y=500)['after'];assert after['y']-before['y']==500
        op('scroll',selector='#end',mode='intoView');assert op('read')['scroll']['y']>500
        frames=op('frames');frame=next(f for f in frames if f['frameId']!=0)
        op('click',frameId=frame['frameId'],selector='#frame-button');assert 'frame:clicked' in op('read',frameId=frame['frameId'])['text']
        shot=op('screenshot',format='png');assert shot['mimeType']=='image/png'
        batch=op('batch',steps=[{'op':'fill','args':{'selector':'#text','value':'batch'}},{'op':'inspect','args':{'selector':'#text'}}]);assert batch['completed']==2 and batch['results'][1]['result']['value']=='batch'
        batch=op('batch',steps=[{'op':'inspect','args':{'selector':'#text'}},{'op':'click','args':{'selector':'#disabled'}},{'op':'click','args':{'selector':'#click'}}]);assert batch['completed']==1 and batch['error']['index']==1
        matches=op('locate',role='button',name='Click fixture',exact=True);assert matches['count']==1
        op('click',role='button',name='Click fixture',exact=True);assert text('#click-status')=='clicks:2'
        assert op('locate',label='Text',exact=True)['count']==1
        assert op('locate',testId='fixture-click')['count']==1
        assert op('locate',role='button',name='Shadow button',exact=True)['count']==1
        assert op('locate',textQuery='Click fixture',exact=True)['count']==1
        nested_match=op('locate',textQuery='Nested action',exact=True);assert nested_match['count']==1 and nested_match['elements'][0]['tag']=='button'
        op('click',textQuery='Nested action',exact=True)
        rejects('click','NOT_UNIQUE',role='button',name='Duplicate',exact=True)
        other=open_page('?other=1');assert any(t['id']==other for t in operation('tabs'))
        operation('fill',{'tabId':other,'selector':'#text','value':'other page'});assert inspect('#text')['value']=='batch'
        if concurrent: concurrent(tab,other)
        operation('activate',{'tabId':other});operation('navigate',{'tabId':other,'url':fixture_url+'?nav=1','waitUntil':'complete'});operation('back',{'tabId':other,'waitUntil':'complete'});operation('forward',{'tabId':other,'waitUntil':'complete'});operation('reload',{'tabId':other,'waitUntil':'complete'})
        large=open_page('?large');page=operation('read',{'tabId':large,'maxElements':5,'textLimit':100});assert len(page['elements'])==5 and page['nextOffset'] is not None and page['textTruncated']
        print('PASS: fixed browser actions, forms, keyboard, safety errors, refs, frames, shadow DOM, screenshots, batch, semantic discovery and multiple pages.',flush=True)
    finally:
        for tab in reversed(pages):
            try:operation('close',{'tabId':tab})
            except RuntimeError:pass
