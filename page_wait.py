"""Wait for a page to stop changing, and recover clicks on hidden menu entries.

Everything here uses fixed read/click/navigate operations through an injected
dispatcher. Waiting is best effort: a read failure ends the wait without
failing the caller's action, and an action is never repeated except the one
documented recovery click (the first click was rejected as not visible, so it
did nothing).
"""
import re
import time
from urllib.parse import urljoin

SETTLE_LIMIT = 6.0
SETTLE_INTERVAL = 0.4
SETTLE_REPEATS = 2
READ_ELEMENTS = 400
MAX_READ_FAILURES = 8
HIDDEN_MARKERS = ('NOT_VISIBLE', 'does not intersect the rendered viewport')
MENU_WORDS = re.compile(r'main menu|navigation panel|toggle (the )?menu|open menu|show menu|menu principale|navigation|hamburger|\bmenu\b', re.I)


def _tab(values):
    return {} if values.get('tabId') is None else {'tabId': values['tabId']}


def read_page(dispatch, values, elements=READ_ELEMENTS, text=False):
    args = {**_tab(values), 'text': bool(text), 'maxElements': elements, 'selectors': False}
    if text:
        args['textLimit'] = 600
    page = dispatch('read', args)
    return page if isinstance(page, dict) else {}


def visible_elements(page):
    result = []
    for element in page.get('elements') or []:
        if isinstance(element, dict) and element.get('visible') and element.get('enabled', True) and element.get('ref'):
            name = element.get('accessibleName') or element.get('text') or element.get('placeholder') or ''
            result.append({'ref': element['ref'], 'tag': element.get('tag', ''), 'type': element.get('type', ''),
                           'name': str(name).strip()[:60], 'href': str(element.get('href') or '')[:200]})
    return result


def settle(dispatch, values, *, need_ready=False, limit=SETTLE_LIMIT,
           clock=time.monotonic, sleep=time.sleep):
    """Poll until the visible-element count is equal for SETTLE_REPEATS further reads.

    After a URL change (need_ready) the document must also report readyState complete.
    Returns a small evidence dict; never raises.
    """
    start = clock()
    previous, same, count, ready, failures = -1, 0, 0, not need_ready, 0
    while True:
        # Reads start SETTLE_INTERVAL apart: the time a read spends on the
        # network already counts toward the pause before the next read.
        read_started = clock()
        try:
            page = read_page(dispatch, values)
        except Exception:
            # A document swap can briefly remove the page handler: tolerate a few failed reads.
            page = None
            failures += 1
            if failures >= MAX_READ_FAILURES:
                return {'stable': False, 'elements': count, 'waitedMs': int((clock() - start) * 1000), 'readFailed': True}
        if page is not None:
            failures = 0
            count = len(visible_elements(page))
            ready = not need_ready or page.get('readyState') == 'complete'
            same = same + 1 if count == previous else 0
            previous = count
            if same >= SETTLE_REPEATS and ready and count > 0:
                return {'stable': True, 'elements': count, 'waitedMs': int((clock() - start) * 1000)}
        if clock() - start >= limit:
            return {'stable': False, 'elements': count, 'waitedMs': int((clock() - start) * 1000)}
        pause = SETTLE_INTERVAL - (clock() - read_started)
        if pause > 0:
            sleep(pause)


def is_hidden_error(error):
    text = str(error)
    return any(marker in text for marker in HIDDEN_MARKERS)


def _same_target(element, wanted):
    return element['name'] == wanted['name'] and element['href'] == wanted['href']


def _find_target(page, values):
    elements = visible_elements(page)
    everything = []
    for element in page.get('elements') or []:
        if isinstance(element, dict) and element.get('ref'):
            name = element.get('accessibleName') or element.get('text') or element.get('placeholder') or ''
            everything.append({'ref': element['ref'], 'tag': element.get('tag', ''), 'type': element.get('type', ''),
                               'name': str(name).strip()[:60], 'href': str(element.get('href') or '')[:200]})
    if values.get('ref'):
        for element in everything:
            if element['ref'] == values['ref']:
                return element, elements
    wanted = values.get('name') or values.get('textQuery')
    if wanted:
        for element in everything:
            if element['name'].lower() == str(wanted).lower() or (not values.get('exact') and str(wanted).lower() in element['name'].lower()):
                return element, elements
    return None, elements


def _menu_button(elements):
    for element in elements:
        if element['tag'] in ('button', 'a', 'div', 'span', 'summary') and MENU_WORDS.search(element['name']):
            if element['tag'] == 'a' and element['href'] and not element['href'].startswith('#'):
                continue
            return element
    return None


def click_with_recovery(run, dispatch, values, *, clock=time.monotonic, sleep=time.sleep):
    """run(op, values) performs a full command (with navigation checks); dispatch is raw.

    If the click is rejected because the entry is hidden (closed side menu): follow its
    link when it has a real href, else open the main menu and click the same name+href again.
    Returns (result, recovery) where recovery is None when no recovery was needed.
    """
    try:
        return run('click', values), None
    except RuntimeError as error:
        if not is_hidden_error(error):
            raise
        first_error = error
    try:
        page = read_page(dispatch, values)
        target, elements = _find_target(page, values)
    except Exception:
        raise first_error
    if target is None:
        raise first_error
    href = target['href']
    if href and not href.startswith('#') and not href.lower().startswith('javascript:'):
        destination = urljoin(page.get('url') or '', href)
        if not destination.lower().startswith(('http://', 'https://')):
            raise first_error
        result = run('navigate', {**_tab(values), 'url': destination, 'waitUntil': 'complete'})
        return result, {'recovery': 'followed_href', 'name': target['name'], 'href': href}
    menu = _menu_button(elements)
    if menu is None:
        raise first_error
    run('click', {**_tab(values), 'ref': menu['ref']})
    settle(dispatch, values, limit=3.0, clock=clock, sleep=sleep)
    page = read_page(dispatch, values)
    again = [e for e in visible_elements(page) if _same_target(e, target)]
    if not again:
        raise first_error
    result = run('click', {**_tab(values), 'ref': again[0]['ref']})
    return result, {'recovery': 'opened_menu_and_clicked', 'menu': menu['name'], 'name': target['name'], 'href': href}


def annotate(result, **extra):
    """Attach evidence to dict results; other result shapes are returned unchanged."""
    if isinstance(result, dict) and extra:
        return {**result, **extra}
    return result
