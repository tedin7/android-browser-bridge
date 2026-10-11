"""Navigation completion and compound MCP ordering regressions; no user browser."""
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from browser_navigation import execute_navigation, NavigationError
from command_order import CommandOrder
from mcp_server import execute_browser_command


def snapshot(url='https://example.org/page',document='document-a',state='complete'):
    return {'url':url,'documentId':document,'readyState':state}


class Clock:
    def __init__(self):self.now=0
    def monotonic(self):return self.now
    def sleep(self,delay):self.now+=delay


class NavigationTests(unittest.TestCase):
    def verify(self,operation,reads,args=None):
        reads=iter(reads);calls=[]
        def dispatch(op,values):
            calls.append((op,values))
            if op=='read':
                result=next(reads)
                if isinstance(result,Exception):raise result
                return result
            return {'id':7}
        clock=Clock()
        with patch('browser_navigation.time.monotonic',clock.monotonic),patch('browser_navigation.time.sleep',clock.sleep):
            result=execute_navigation(dispatch,operation,{'tabId':7,'waitUntil':'complete','timeoutMs':1000,**(args or {})})
        self.assertEqual(result,{'id':7})
        actions=[values for op,values in calls if op==operation]
        self.assertEqual(len(actions),1);self.assertEqual(actions[0]['waitUntil'],'none')
        self.assertTrue(all(values.get('maxElements')==0 and values.get('text') is False for op,values in calls if op=='read'))
        return calls

    def test_bfcache_changed_url_even_when_document_identity_is_restored(self):
        self.verify('forward',[snapshot(),snapshot(),snapshot('https://example.org/next')])

    def test_same_url_reload_requires_new_document(self):
        self.verify('reload',[snapshot(),snapshot(),snapshot(document='document-b')])

    def test_fragment_navigation_counts_as_same_document_transition(self):
        self.verify('back',[snapshot('https://example.org/page#two'),snapshot('https://example.org/page#one')])

    def test_stale_complete_and_transient_read_failure_do_not_replay_navigation(self):
        calls=self.verify('navigate',[snapshot(),snapshot(),RuntimeError('message handler replaced'),snapshot('https://example.org/new',state='loading'),snapshot('https://example.org/new')],{'url':'https://example.org/new'})
        self.assertEqual(sum(op=='read' for op,_ in calls),5)

    def test_open_reads_returned_tab_instead_of_previous_active_tab(self):
        calls=self.verify('open',[RuntimeError('initial about blank'),snapshot()],{'tabId':99})
        self.assertTrue(all(args['tabId']==7 for op,args in calls if op=='read'))
        self.assertEqual(calls[0][0],'open')

    def test_timeout_dispatches_navigation_once_and_remains_uncertain(self):
        calls=[]
        def dispatch(op,args):calls.append(op);return snapshot() if op=='read' else {'id':7}
        clock=Clock()
        with patch('browser_navigation.time.monotonic',clock.monotonic),patch('browser_navigation.time.sleep',clock.sleep):
            with self.assertRaisesRegex(NavigationError,'NAVIGATION_TIMEOUT'):
                execute_navigation(dispatch,'reload',{'tabId':7,'waitUntil':'complete','timeoutMs':50})
        self.assertEqual(calls.count('reload'),1);self.assertGreater(calls.count('read'),1)

    def test_precondition_failure_happens_before_any_navigation(self):
        for response in [RuntimeError('page suspended'),{},snapshot('about:blank')]:
            calls=[]
            def dispatch(op,args):
                calls.append(op)
                if isinstance(response,Exception):raise response
                return response
            with self.subTest(response=type(response).__name__),self.assertRaisesRegex(NavigationError,'NAVIGATION_PRECONDITION'):
                execute_navigation(dispatch,'back',{'tabId':7,'waitUntil':'complete'})
            self.assertEqual(calls,['read'])

    def test_protected_previous_page_can_navigate_to_http(self):
        self.verify('navigate',[RuntimeError('Only HTTP(S) page URLs allowed'),snapshot()],{'url':'https://example.org/page'})

    def test_invalid_timeout_never_dispatches(self):
        for timeout in [True,float('nan'),'10']:
            dispatch=Mock()
            with self.subTest(timeout=timeout),self.assertRaises(ValueError):execute_navigation(dispatch,'reload',{'waitUntil':'complete','timeoutMs':timeout})
            dispatch.assert_not_called()

    def test_batch_navigation_timeout_stops_before_later_action(self):
        calls=[]
        def dispatch(url,token,device,op,args,**kwargs):
            calls.append((op,args));return snapshot() if op=='read' else {'value':'ready'}
        steps=[{'op':'inspect','args':{'selector':'#ready'}},{'op':'forward','args':{'waitUntil':'complete','timeoutMs':0}},{'op':'click','args':{'selector':'#later'}}]
        with patch('mcp_server.run_command',side_effect=dispatch),patch('mcp_server.COMMAND_ORDER',CommandOrder()):
            result=execute_browser_command('http://127.0.0.1:1','test','fixture','batch',{'tabId':7,'steps':steps})
        self.assertEqual(result['completed'],1);self.assertEqual(result['error']['index'],1)
        self.assertEqual(result['error']['code'],'NAVIGATION_TIMEOUT');self.assertTrue(result['error']['actionMayHaveOccurred'])
        self.assertEqual(sum(op=='forward' for op,_ in calls),1);self.assertFalse(any(op=='click' for op,_ in calls))
        self.assertTrue(all(args.get('tabId')==7 for _,args in calls))


class OrderingTests(unittest.TestCase):
    def wait_queued(self,order,count):
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            with order.changed:
                if len(order.waiting)>=count:return
            time.sleep(.001)
        self.fail('Expected coordinator waiting tickets')

    def test_same_page_fifo_and_independent_pages_parallel(self):
        order=CommandOrder();release=threading.Event();started=threading.Event();events=[]
        def first():
            with order.enter('fixture','navigate',{'tabId':1}):events.append('first');started.set();self.assertTrue(release.wait(2))
        def next_page(label,tab):
            with order.enter('fixture','read',{'tabId':tab}):events.append(label)
        with ThreadPoolExecutor(max_workers=3) as pool:
            a=pool.submit(first);self.assertTrue(started.wait(1));b=pool.submit(next_page,'second',1);self.wait_queued(order,1)
            c=pool.submit(next_page,'independent',2)
            try:c.result(timeout=1);self.assertEqual(events,['first','independent'])
            finally:release.set()
            a.result(timeout=1);b.result(timeout=1)
        self.assertEqual(events,['first','independent','second'])

    def test_global_barrier_waits_for_earlier_page_and_blocks_later_page(self):
        order=CommandOrder();release_page=threading.Event();release_barrier=threading.Event();page_started=threading.Event();barrier_started=threading.Event();later_started=threading.Event()
        def page():
            with order.enter('fixture','read',{'tabId':1}):page_started.set();release_page.wait(2)
        def barrier():
            with order.enter('fixture','open',{}):barrier_started.set();release_barrier.wait(2)
        def later():
            with order.enter('fixture','read',{'tabId':2}):later_started.set()
        with ThreadPoolExecutor(max_workers=3) as pool:
            a=pool.submit(page);self.assertTrue(page_started.wait(1));b=pool.submit(barrier);self.wait_queued(order,1);c=pool.submit(later);self.wait_queued(order,2)
            try:
                self.assertFalse(barrier_started.is_set());release_page.set();self.assertTrue(barrier_started.wait(1));self.assertFalse(later_started.is_set())
                release_barrier.set();self.assertTrue(later_started.wait(1))
            finally:release_page.set();release_barrier.set()
            for task in [a,b,c]:task.result(timeout=1)

    def test_global_barrier_does_not_block_another_device(self):
        order=CommandOrder()
        with order.enter('one','open',{}),ThreadPoolExecutor(max_workers=1) as pool:
            def other():
                with order.enter('two','read',{'tabId':1}):return True
            self.assertTrue(pool.submit(other).result(timeout=1))

    def test_malformed_input_and_body_exception_leave_coordinator_usable(self):
        order=CommandOrder()
        for args in [None,{'tabId':True},{'tabId':'1'}]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                with order.enter('fixture','read',args):pass
        for device,operation in [(None,'read'),('fixture',None)]:
            with self.assertRaises(ValueError):
                with order.enter(device,operation,{}):pass
        with self.assertRaises(RuntimeError):
            with order.enter('fixture','read',{'tabId':1}):raise RuntimeError('operation failed')
        with order.enter('fixture','open',{}):pass
        self.assertFalse(order.waiting);self.assertFalse(order.active);self.assertFalse(order.global_devices)


if __name__=='__main__':unittest.main()
