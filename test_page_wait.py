import unittest
from unittest.mock import patch
import page_wait


def element(ref, name, href='', tag='a', visible=True):
    return {'ref': ref, 'tag': tag, 'accessibleName': name, 'href': href, 'visible': visible, 'enabled': True}


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class SettleTest(unittest.TestCase):
    def run_settle(self, counts, **kwargs):
        clock, reads = Clock(), iter(counts)
        def dispatch(op, args):
            value = next(reads, counts[-1])
            if isinstance(value, Exception):
                raise value
            return value
        return page_wait.settle(dispatch, {'tabId': 1}, clock=clock, sleep=clock.sleep, **kwargs), clock

    def page(self, n, state='complete'):
        return {'readyState': state, 'elements': [element('e%d' % i, 'x%d' % i) for i in range(n)]}

    def test_waits_until_count_is_stable_for_two_further_reads(self):
        evidence, clock = self.run_settle([self.page(3), self.page(5), self.page(9), self.page(9), self.page(9)])
        self.assertTrue(evidence['stable'])
        self.assertEqual(evidence['elements'], 9)
        self.assertAlmostEqual(clock.now, 4 * page_wait.SETTLE_INTERVAL)

    def test_read_time_counts_toward_the_pause_between_reads(self):
        clock, starts = Clock(), []
        def dispatch(op, args):
            starts.append(clock.now)
            clock.now += 0.15  # a read over the network
            return self.page(4)
        evidence = page_wait.settle(dispatch, {'tabId': 1}, clock=clock, sleep=clock.sleep)
        self.assertTrue(evidence['stable'])
        self.assertEqual(len(starts), 3)
        for earlier, later in zip(starts, starts[1:]):
            self.assertAlmostEqual(later - earlier, page_wait.SETTLE_INTERVAL)
        self.assertAlmostEqual(clock.now, 2 * page_wait.SETTLE_INTERVAL + 0.15)

    def test_slow_reads_are_not_followed_by_a_pause(self):
        clock, sleeps = Clock(), []
        def dispatch(op, args):
            clock.now += 0.5
            return self.page(4)
        def sleep(seconds):
            sleeps.append(seconds)
            clock.sleep(seconds)
        evidence = page_wait.settle(dispatch, {'tabId': 1}, clock=clock, sleep=sleep)
        self.assertTrue(evidence['stable'])
        self.assertEqual(sleeps, [])
        self.assertAlmostEqual(clock.now, 1.5)

    def test_gives_up_after_the_limit(self):
        counter = iter(range(1000))
        clock = Clock()
        evidence = page_wait.settle(lambda op, args: self.page(next(counter) + 1), {}, clock=clock, sleep=clock.sleep)
        self.assertFalse(evidence['stable'])
        self.assertLessEqual(clock.now, page_wait.SETTLE_LIMIT + page_wait.SETTLE_INTERVAL)

    def test_after_url_change_requires_ready_state_complete(self):
        evidence, _ = self.run_settle([self.page(4, 'loading')] * 3 + [self.page(4)] * 4, need_ready=True)
        self.assertTrue(evidence['stable'])
        evidence, _ = self.run_settle([self.page(4, 'loading')], need_ready=True)
        self.assertFalse(evidence['stable'])

    def test_read_errors_do_not_raise_and_stop_early(self):
        evidence, clock = self.run_settle([RuntimeError('gone')])
        self.assertFalse(evidence['stable'])
        self.assertTrue(evidence['readFailed'])
        self.assertLess(clock.now, 4)

    def test_one_failed_read_during_a_document_swap_is_tolerated(self):
        evidence, _ = self.run_settle([self.page(4), RuntimeError('swap'), self.page(4), self.page(4), self.page(4)])
        self.assertTrue(evidence['stable'])

    def test_hidden_elements_are_not_counted(self):
        page = {'elements': [element('a', 'A'), element('b', 'B', visible=False)]}
        self.assertEqual(len(page_wait.visible_elements(page)), 1)


class ClickRecoveryTest(unittest.TestCase):
    HIDDEN = RuntimeError('NOT_VISIBLE: Element does not intersect the rendered viewport')

    def setUp(self):
        self.calls = []
        self.clock = Clock()

    def make_run(self, hidden_refs):
        def run(op, values):
            self.calls.append((op, dict(values)))
            if op == 'click' and values.get('ref') in hidden_refs:
                raise self.HIDDEN
            return {'ok': True}
        return run

    def recover(self, run, pages, values):
        reads = iter(pages)
        return page_wait.click_with_recovery(run, lambda op, args: next(reads), values, clock=self.clock, sleep=self.clock.sleep)

    def test_normal_click_needs_no_recovery(self):
        result, recovery = self.recover(self.make_run(set()), [], {'tabId': 1, 'ref': 'e1'})
        self.assertEqual(result, {'ok': True})
        self.assertIsNone(recovery)
        self.assertEqual(len(self.calls), 1)

    def test_other_errors_propagate(self):
        def run(op, values):
            raise RuntimeError('COVERED: nope')
        with self.assertRaises(RuntimeError):
            self.recover(run, [], {'tabId': 1, 'ref': 'e1'})

    def test_hidden_entry_with_href_navigates_to_it(self):
        page = {'url': 'https://site.test/a/b', 'elements': [element('e1', 'Payments', '/payments', visible=False)]}
        result, recovery = self.recover(self.make_run({'e1'}), [page], {'tabId': 1, 'ref': 'e1'})
        self.assertEqual(recovery['recovery'], 'followed_href')
        self.assertEqual(self.calls[-1][0], 'navigate')
        self.assertEqual(self.calls[-1][1]['url'], 'https://site.test/payments')

    def test_hidden_entry_without_href_opens_main_menu_then_clicks_same_entry(self):
        hidden = [element('e1', 'Reports', '#', visible=False), element('m1', 'Main menu', tag='button')]
        opened = [element('e1', 'Reports', '#', visible=False), element('n9', 'Reports', '#'), element('m1', 'Main menu', tag='button')]
        stable = {'elements': opened}
        result, recovery = self.recover(self.make_run({'e1'}), [{'url': 'https://s.test/', 'elements': hidden}] + [stable] * 6, {'tabId': 1, 'ref': 'e1'})
        self.assertEqual(recovery['recovery'], 'opened_menu_and_clicked')
        self.assertEqual([c[1].get('ref') for c in self.calls if c[0] == 'click'], ['e1', 'm1', 'n9'])

    def test_no_menu_button_reports_the_original_error(self):
        page = {'url': 'https://s.test/', 'elements': [element('e1', 'Reports', '#', visible=False)]}
        with self.assertRaises(RuntimeError) as caught:
            self.recover(self.make_run({'e1'}), [page], {'tabId': 1, 'ref': 'e1'})
        self.assertIn('NOT_VISIBLE', str(caught.exception))

    def test_javascript_href_is_never_followed(self):
        page = {'url': 'https://s.test/', 'elements': [element('e1', 'X', 'javascript:alert(1)', visible=False)]}
        with self.assertRaises(RuntimeError):
            self.recover(self.make_run({'e1'}), [page], {'tabId': 1, 'ref': 'e1'})
        self.assertNotIn('navigate', [c[0] for c in self.calls])


if __name__ == '__main__':
    unittest.main()
