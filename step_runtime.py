"""Bounded declarative browser actions with read-only outcome checks.

The injected dispatch(op, args, timeout_ms) must respect its timeout and must not
retry mutating actions. This module does not grant cross-broker tab ownership.
"""
import copy
import json
import re
import time
from operation_registry import operation_contract, validate_arguments, _validate

ACTIONS = frozenset({'click','double_click','fill','type','clear','select','check','press','focus','hover','scroll','navigate','reload','back','forward','wait','read','inspect','locate'})
READ_ONLY = frozenset({'read','inspect','locate','wait'})
TARGET_FIELDS = frozenset({'selector','ref','role','name','label','testId','textQuery','exact','frameId'})


def _invalid(message):
    raise ValueError('INVALID_ARGUMENT: ' + message)


def _validate_reference(value, before):
    if isinstance(value, dict):
        if '$result' in value:
            ref = value['$result']
            if set(value) != {'$result'} or not isinstance(ref, dict) or set(ref) != {'step','path'}:
                _invalid('Invalid result reference')
            index, path = ref['step'], ref['path']
            if isinstance(index,bool) or not isinstance(index,int) or not 0 <= index < before:
                _invalid('References must name an earlier step')
            if not isinstance(path,list) or not 1 <= len(path) <= 8 or any(not isinstance(key,(str,int)) or isinstance(key,bool) or (isinstance(key,str) and (not key or len(key)>128)) or (isinstance(key,int) and key<0) for key in path):
                _invalid('Invalid result path')
        else:
            for item in value.values(): _validate_reference(item,before)
    elif isinstance(value,list):
        for item in value: _validate_reference(item,before)


def _validate_step_arguments(op, args):
    # A reference has no value yet. Validate the rest of its enclosing schema
    # now; validate the concrete value with the full schema before dispatch.
    def specialized(schema, value):
        if isinstance(value, dict) and set(value) == {'$result'}:
            return {}
        schema = copy.deepcopy(schema)
        if isinstance(value, dict):
            properties=schema.get('properties', {})
            schema['properties']={key:specialized(rule,value[key]) if key in value else rule for key,rule in properties.items()}
        elif isinstance(value,list) and value:
            # References in arrays would require per-position schemas. Keep v1
            # references at named argument fields rather than loosening arrays.
            def contains_ref(item):
                return isinstance(item,dict) and ('$result' in item or any(contains_ref(v) for v in item.values())) or isinstance(item,list) and any(contains_ref(v) for v in item)
            if any(contains_ref(item) for item in value): _invalid('Result references inside arrays are unsupported')
        return schema
    _validate(specialized(operation_contract(op)['inputSchema'], args), args, 'args')


def _condition(condition, before):
    if not isinstance(condition,dict) or set(condition)-{'kind','args','expected','match'}:
        _invalid('Invalid condition')
    kind=condition.get('kind')
    if kind not in {'presence','value','text','url'}: _invalid('Unsupported condition kind')
    expected=condition.get('expected')
    if kind=='presence':
        if not isinstance(expected,bool): _invalid('Presence expected must be boolean')
    elif not isinstance(expected,str) or len(expected)>4000:
        _invalid('Condition expected must be a bounded string')
    if condition.get('match','equals') not in {'equals','contains'} or (kind=='presence' and 'match' in condition):
        _invalid('Invalid condition comparison')
    args=condition.get('args',{})
    if not isinstance(args,dict) or set(args)-TARGET_FIELDS:
        _invalid('Condition arguments must identify a target')
    if kind in {'presence','value'} and not any(key in args for key in TARGET_FIELDS-{'frameId','exact'}):
        _invalid('Presence/value conditions require a target')
    _validate_reference(args,before)
    if kind=='url' and args: _invalid('URL checks do not accept a target')
    _validate_step_arguments({'presence':'locate','value':'inspect','text':'read','url':'read'}[kind],args)


def validate_plan(plan):
    if not isinstance(plan,dict) or set(plan)-{'tabId','steps','preconditions','verify','timeoutMs','outputFields'}:
        _invalid('Unknown browser_step argument')
    tab=plan.get('tabId')
    if isinstance(tab,bool) or not isinstance(tab,int) or tab<0: _invalid('Explicit tabId is required')
    timeout=plan.get('timeoutMs',60000)
    if isinstance(timeout,bool) or not isinstance(timeout,int) or not 1 <= timeout <= 60000:
        _invalid('timeoutMs must be 1..60000')
    steps=plan.get('steps')
    if not isinstance(steps,list) or not 1 <= len(steps) <= 25: _invalid('Expected 1..25 steps')
    for index,step in enumerate(steps):
        if not isinstance(step,dict) or set(step)-{'op','args'} or step.get('op') not in ACTIONS:
            _invalid('Only fixed supported step operations are accepted')
        args=step.get('args',{})
        if not isinstance(args,dict) or 'tabId' in args: _invalid('Step args inherit the workflow tabId')
        _validate_reference(args,index)
        _validate_step_arguments(step['op'],{'tabId':tab,**args})
    for name,before in (('preconditions',0),('verify',len(steps))):
        conditions=plan.get(name,[])
        if not isinstance(conditions,list) or len(conditions)>10: _invalid('At most 10 conditions are permitted')
        for condition in conditions: _condition(condition,before)
    fields=plan.get('outputFields',[])
    if not isinstance(fields,list) or len(fields)>32 or any(not isinstance(field,str) or not field or len(field)>128 or field=='data' for field in fields):
        _invalid('Invalid outputFields')
    try:
        if len(json.dumps(plan,allow_nan=False).encode())>65536: _invalid('Plan exceeds 64 KiB')
    except (TypeError,OverflowError): _invalid('Plan must contain JSON data')
    return copy.deepcopy(plan)


def _resolve(value, results):
    if isinstance(value,dict):
        if '$result' in value:
            ref=value['$result']; item=results[ref['step']]
            for key in ref['path']:
                if isinstance(item,dict) and isinstance(key,str) and key in item: item=item[key]
                elif isinstance(item,list) and isinstance(key,int) and 0 <= key < len(item): item=item[key]
                else: raise ValueError('RESULT_REFERENCE_UNAVAILABLE')
            return copy.deepcopy(item)
        return {key:_resolve(item,results) for key,item in value.items()}
    if isinstance(value,list): return [_resolve(item,results) for item in value]
    return value


def execute_step(plan, dispatch, *, clock=time.monotonic, sleep=time.sleep):
    plan=validate_plan(plan)
    deadline=clock()+plan.get('timeoutMs',60000)/1000
    results=[]; may_have_acted=False; observations=[]
    def remaining():
        return max(0,int((deadline-clock())*1000))
    def call(op,args):
        budget=remaining()
        if budget<=0: raise TimeoutError('STEP_DEADLINE')
        values={'tabId':plan['tabId'],**args}
        validate_arguments(op, values)
        value=dispatch(op,values,budget)
        if remaining()<=0: raise TimeoutError('STEP_DEADLINE')
        if isinstance(value,dict) and value.get('error'): raise RuntimeError('BACKEND_ERROR')
        return value
    def check(condition):
        kind=condition['kind']; args=_resolve(condition.get('args',{}),results)
        if kind=='presence':
            value=call('locate',{**args,'maxElements':1,'selectors':False})
            actual=bool(value.get('elements'))
        elif kind=='value':
            value=call('inspect',args); actual=value.get('value')
        elif kind=='text':
            # Bound observation at its producer. A truncated mismatch is inconclusive.
            value=call('read',{**args,'maxElements':0,'textLimit':4000,'selectors':False})
            actual=value.get('text')
        else:
            value=call('read',{'maxElements':0,'textLimit':0,'selectors':False})
            actual=value.get('url')
        expected=condition['expected']
        matched=(expected in actual if isinstance(actual,str) and condition.get('match')=='contains' else actual==expected)
        incomplete=bool(value.get('textTruncated')) if kind=='text' else False
        if kind=='text' and incomplete and condition.get('match','equals')=='equals': matched=False
        return {'kind':kind,'matched':matched,'complete':not incomplete}
    def receipt(state, **extra):
        value={'state':state,'tabId':plan['tabId'],'completed':len(results),'verified':state=='verified','actionMayHaveOccurred':may_have_acted,'evidence':observations,**extra}
        if results and plan.get('outputFields') and isinstance(results[-1],dict):
            selected={key:results[-1][key] for key in plan['outputFields'] if key in results[-1]}
            if len(json.dumps(selected,ensure_ascii=False).encode())<=14000: value['output']=selected
            else: value.update(outputOmitted=True,nextSteps=['Use a targeted browser_command read to retrieve the required fields.'])
        return value
    try:
        for condition in plan.get('preconditions',[]):
            evidence=check(condition); observations.append(evidence)
            if not evidence['matched']:
                return receipt('precondition_failed',nextSteps=['Inspect the current tab and revise the precondition before any action.'])
        observations=[]
        for step in plan['steps']:
            args=_resolve(step.get('args',{}),results)
            if remaining()<=0: raise TimeoutError('STEP_DEADLINE')
            if step['op'] not in READ_ONLY: may_have_acted=True
            results.append(call(step['op'],args))
        if not plan.get('verify'): return receipt('executed')
        while remaining()>0:
            observations=[check(condition) for condition in plan['verify']]
            if all(item['matched'] for item in observations): return receipt('verified')
            sleep(min(.1,remaining()/1000))
        return receipt('verification_failed',nextSteps=['Inspect current state; actions completed but the requested outcome was not verified. Do not repeat automatically.'])
    except TimeoutError:
        state='verification_failed' if len(results)==len(plan['steps']) else 'unknown' if may_have_acted else 'not_executed'
        return receipt(state,code='STEP_DEADLINE',nextSteps=['Recover any available command ID and inspect the current tab before deciding whether another action is needed.'])
    except Exception as error:
        # Backend error strings may contain page contents; keep diagnostics bounded.
        ids={}
        for label,key in [('Command','commandId'),('Action','actionId')]:
            found=re.search(label+r' ID: ([A-Za-z0-9_-]{16,128})',str(error))
            if found:ids[key]=found.group(1)
        return receipt('unknown' if may_have_acted else 'not_executed',**ids,code='STEP_FAILED',errorType=type(error).__name__,nextSteps=['Inspect the tab and backend command status. A dispatched action must not be repeated automatically.'])
