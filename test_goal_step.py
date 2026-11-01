import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import goal_step
import jev_client
import mcp_server


def el(ref, name, href='', tag='a'):
    return {'ref': ref, 'tag': tag, 'accessibleName': name, 'href': href, 'visible': True, 'enabled': True}


class FakeJev:
    JevUnavailable = jev_client.JevUnavailable

    def __init__(self, arrived, picks, key=True):
        self.arrived, self.picks, self.key = list(arrived), list(picks), key
        self.pick_calls = []

    def available(self):
        return self.key

    def yes_probability(self, state, instructions):
        return self.arrived.pop(0)

    def choose(self, state, instructions, criteria):
        self.pick_calls.append(criteria)
        return self.picks.pop(0)


class Browser:
    """pages: list of page dicts served in order; a click advances to the next page."""
    def __init__(self, pages):
        self.pages, self.index, self.clicks = pages, 0, []
    def read(self, op, args):
        return {'text': 'text', 'title': 't', **self.pages[self.index]}
    def run(self, op, values):
        self.clicks.append(values['ref'])
        self.index = min(self.index + 1, len(self.pages) - 1)
        return {'ok': True}


def page(url, *elements):
    return {'url': url, 'elements': list(elements)}


class GoalTest(unittest.TestCase):
    def go(self, browser, jev, **args):
        return goal_step.run_goal(browser.run, browser.read, {'tabId': 1, 'goal': 'open reports', **args}, jev=jev)

    def test_confident_pick_clicks_then_arrival_stops(self):
        browser = Browser([page('https://a.test/', el('e1', 'Reports', '/r'), el('e2', 'Home')), page('https://a.test/r', el('e3', 'Back'))])
        jev = FakeJev([0.1, 0.95], [('e0', 0.9)])
        result = self.go(browser, jev)
        self.assertEqual(result['state'], 'arrived')
        self.assertEqual(browser.clicks, ['e1'])
        self.assertEqual(result['path'][0]['click'], 'Reports')

    def test_weak_pick_hands_over_without_clicking_or_opening_menu(self):
        browser = Browser([page('https://a.test/', el('e1', 'Reports'), el('m', 'Main menu', tag='button'))])
        result = self.go(browser, FakeJev([0.1], [('e0', 0.69)]))
        self.assertEqual(result['state'], 'needs_decision')
        self.assertEqual(result['reason'], 'choice_unsure')
        self.assertEqual(browser.clicks, [])
        self.assertEqual({e['ref'] for e in result['elements']}, {'e1', 'm'})

    def test_none_answer_hands_over(self):
        browser = Browser([page('https://a.test/', el('e1', 'Reports'))])
        result = self.go(browser, FakeJev([0.1], [('none', 0.99)]))
        self.assertEqual(result['reason'], 'choice_unsure')

    def test_unclear_arrival_is_left_to_the_model(self):
        browser = Browser([page('https://a.test/', el('e1', 'Reports'))])
        result = self.go(browser, FakeJev([0.5], []))
        self.assertEqual(result['reason'], 'arrival_unclear')
        self.assertEqual(browser.clicks, [])

    def test_below_threshold_means_not_arrived(self):
        browser = Browser([page('https://a.test/', el('e1', 'Reports'))])
        jev = FakeJev([0.19, 0.19], [('e0', 0.8)])
        result = self.go(browser, jev, maxSteps=1)
        self.assertEqual(result['reason'], 'step_limit')

    def test_no_jev_key_still_returns_compact_list(self):
        browser = Browser([page('https://a.test/', el('e1', 'Reports', '/r'))])
        result = self.go(browser, FakeJev([], [], key=False))
        self.assertEqual(result['reason'], 'no_jev_key')
        self.assertEqual(result['elements'], [{'ref': 'e1', 'tag': 'a', 'name': 'Reports', 'href': '/r'}])

    def test_jev_failure_hands_over(self):
        class Broken(FakeJev):
            def yes_probability(self, state, instructions):
                raise jev_client.JevUnavailable('x')
        result = self.go(Browser([page('https://a.test/', el('e1', 'A'))]), Broken([], []))
        self.assertEqual(result['reason'], 'jev_unavailable')

    def test_submenu_new_elements_are_chosen_first(self):
        closed = page('https://a.test/', el('e1', 'Settings', '#', tag='button'), el('e2', 'Reports'))
        opened = page('https://a.test/', el('e1', 'Settings', '#', tag='button'), el('e2', 'Reports'), el('n1', 'Billing'), el('n2', 'Payments'))
        done = page('https://a.test/pay', el('e9', 'x'))
        browser = Browser([closed, opened, done])
        jev = FakeJev([0.0, 0.0, 0.9], [('e0', 0.8), ('e1', 0.9)])
        result = self.go(browser, jev)
        self.assertEqual(browser.clicks, ['e1', 'n2'])
        self.assertEqual(result['path'][1]['how'], 'submenu')
        self.assertEqual(len(jev.pick_calls[1]), 3)  # two new entries + 'none'

    def test_lists_are_split_in_chunks_of_thirty(self):
        elements = [el('e%d' % i, 'Item %d' % i) for i in range(65)]
        jev = FakeJev([0.0], [('e3', 0.5), ('e4', 0.9), ('none', 0.9)])
        index, probability = goal_step.pick('g', {}, goal_step.visible_elements({'elements': elements}), choose=jev.choose)
        self.assertEqual((index, probability), (34, 0.9))
        self.assertEqual([len(c) for c in jev.pick_calls], [31, 31, 6])


class JevClientTest(unittest.TestCase):
    def test_key_from_environment_and_private_file(self):
        self.assertEqual(jev_client.resolve_key({'BROWSER_BRIDGE_JEV_KEY': ' k123 '}), 'k123')
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'env')
            with open(path, 'w') as handle:
                handle.write('OTHER=1\nTYPESAFE_API_KEY="abc"\n')
            os.chmod(path, 0o600)
            self.assertEqual(jev_client.resolve_key({'BROWSER_BRIDGE_JEV_KEY_FILE': path}), 'abc')
            os.chmod(path, 0o644)
            with self.assertRaises(jev_client.JevUnavailable):
                jev_client.resolve_key({'BROWSER_BRIDGE_JEV_KEY_FILE': path})

    def test_missing_key_is_unavailable(self):
        with self.assertRaises(jev_client.JevUnavailable):
            jev_client.resolve_key({'BROWSER_BRIDGE_JEV_KEY_FILE': '/nonexistent/file'})

    def test_retries_503_only_and_never_leaks_the_key(self):
        class Response:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(self.body).encode()
        calls = []
        def opener(request, timeout):
            calls.append(request.get_header('Authorization'))
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 503, 'busy', {}, io.BytesIO())
            return Response({'answers': {'q': {'noul': 0.9}}})
        environ = {'BROWSER_BRIDGE_JEV_KEY': 'SECRETKEY'}
        value = jev_client.yes_probability({'a': 1}, 'ok?', opener=opener, sleep=lambda s: None, environ=environ)
        self.assertEqual(value, 0.9)
        self.assertEqual(len(calls), 2)
        def failing(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, 'no', {}, io.BytesIO())
        with self.assertRaises(jev_client.JevUnavailable) as caught:
            jev_client.ask({}, {}, opener=failing, sleep=lambda s: None, environ=environ)
        self.assertNotIn('SECRETKEY', str(caught.exception))

    def test_choose_returns_top_probability(self):
        body = {'answers': {'pick': {'choice': 'e2', 'probabilities': {'e2': 0.8, 'none': 0.2}}}}
        with patch.object(jev_client, 'ask', return_value=body):
            self.assertEqual(jev_client.choose({}, 'i', {'e2': 'x'}), ('e2', 0.8))


class McpIntegrationTest(unittest.TestCase):
    """execute_browser_command waits after navigate/click and reports the recovery."""
    def run_command(self, calls, reads, hidden=False):
        def fake(url, token, device, op, values, **kwargs):
            calls.append((op, dict(values)))
            if op == 'read':
                return reads.pop(0) if len(reads) > 1 else reads[0]
            if op == 'click' and hidden and values.get('ref') == 'e1':
                raise RuntimeError('NOT_VISIBLE: Element does not intersect the rendered viewport')
            return {'ok': True}
        return fake

    def test_click_waits_for_stable_page_and_is_annotated(self):
        calls = []
        stable = {'readyState': 'complete', 'url': 'https://a.test/', 'elements': [el('e%d' % i, 'n%d' % i) for i in range(5)]}
        with patch('mcp_server.run_command', self.run_command(calls, [stable])), patch('page_wait.time.sleep'), patch.dict(os.environ, {}, clear=False):
            result = mcp_server.execute_browser_command('u', 't', 'dev', 'click', {'tabId': 1, 'ref': 'e1'})
        self.assertTrue(result['pageSettle']['stable'])
        self.assertEqual([c[0] for c in calls].count('click'), 1)
        self.assertGreaterEqual([c[0] for c in calls].count('read'), 3)

    def test_hidden_click_follows_href_and_says_so(self):
        calls = []
        page_hidden = {'readyState': 'complete', 'url': 'https://a.test/x', 'elements': [{**el('e1', 'Payments', '/payments'), 'visible': False}]}
        landed = {'readyState': 'complete', 'url': 'https://a.test/payments', 'elements': [el('e%d' % i, 'n%d' % i) for i in range(3)]}
        reads = [page_hidden, page_hidden] + [landed] * 40
        fake = self.run_command(calls, reads, hidden=True)
        with patch('mcp_server.run_command', fake), patch('page_wait.time.sleep'), patch('browser_navigation.time.sleep'):
            result = mcp_server.execute_browser_command('u', 't', 'dev', 'click', {'tabId': 1, 'ref': 'e1'})
        self.assertEqual(result['autoRecovery']['recovery'], 'followed_href')
        self.assertIn('navigate', [c[0] for c in calls])

    def test_auto_wait_can_be_switched_off(self):
        calls = []
        with patch('mcp_server.run_command', self.run_command(calls, [{}])), patch.dict(os.environ, {'BROWSER_BRIDGE_AUTO_WAIT': '0'}):
            result = mcp_server.execute_browser_command('u', 't', 'dev', 'click', {'tabId': 1, 'ref': 'e1'})
        self.assertNotIn('pageSettle', result)
        self.assertEqual([c[0] for c in calls], ['click'])

    def test_goal_tool_is_listed_and_validates_input(self):
        names = [tool['name'] for tool in mcp_server.TOOLS]
        self.assertIn('browser_goal', names)
        reply = mcp_server.handle({'method': 'tools/call', 'params': {'name': 'browser_goal', 'arguments': {'device': 'd', 'tabId': 1, 'goal': ''}}})
        self.assertTrue(reply.get('isError'))


if __name__ == '__main__':
    unittest.main()
