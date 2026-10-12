"""Agent-readable failures and opt-in, fixed local Android foreground helper."""
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

REMEDIES = {
    'HOST_PERMISSION_REQUIRED': ['Firefox restricts extension access to this page or host permission is missing. A browser-generated connection-error page can produce the same error; check site reachability first.', 'For browser settings, installer dialogs or protected Mozilla pages, complete the step in Firefox manually; do not retry page injection or disable browser protections.', 'For an ordinary site, check the extension site-access permission before retrying.'],
    'ACTION_UNCERTAIN': ['Use browser_status with actionId to reconcile this action before considering another mutation.', 'If identity or result retention expired, inspect application state; do not assume the action failed or repeat it automatically.'],
    'LEASE_CONFLICT': ['Another workflow owns this tab; use a separate tab or wait for its lease to finish.'],
    'LEASE_EXPIRED': ['Inspect the current page before starting a new workflow; prior actions may have completed.'],
    'NAVIGATION_PRECONDITION': ['Call foreground for this tab and inspect its state.', 'For a browser connection-error page, first restore server reachability, then submit one reload with waitUntil:none and verify read afterward. Protected browser error pages cannot be read by the extension.'],
    'NAVIGATION_TIMEOUT': ['Inspect read and browser_status before repeating navigation; it was already submitted once.', 'Call foreground if Android suspended the page.'],
    'ANDROID_FOREGROUND_FAILED': ['Open Firefox on Android manually.', 'Check the configured Firefox package and local Termux activity launcher.'],
    'PAGE_RESPONSE_TIMEOUT': ['Call foreground with this tabId and inspect the current page state.', 'The page may be suspended and the action may have occurred; do not blindly repeat a modifying action.'],
    'NOT_EDITABLE': ['Inspect the element type and find an input, textarea or contenteditable control.'],
    'INVALID_TARGET': ['Inspect the target and choose an element compatible with this operation.'],
    'UNSUPPORTED_OPERATION': ['Use viewport only on Firefox desktop; Android viewport follows the device screen.', 'Computed inspect layout requires extension 0.3.1; use basic geometry or update the extension before claiming CSS details.', 'Check capabilities only for the unknown feature.'],
    'CANCELED': ['The page canceled the input event; inspect its validation or required interaction sequence before retrying.'],
    'VIEWPORT_UNAVAILABLE': ['Call foreground for this device and tab.', 'If Firefox remains suspended, open Firefox on Android, then inspect read.viewport before retrying.'],
    'VIEWPORT_MEASUREMENT_UNAVAILABLE': ['The window may already have resized. Inspect read.viewport and use measured dimensions before repeating viewport.', 'Foreground the desktop tab if rendering is suspended.'],
    'TAB_NOT_VISIBLE': ['Call foreground with this tabId.', 'Keep Firefox visible on Android and retry the screenshot after read.viewport is nonzero.'],
    'NOT_FOUND': ['Use locate or read to discover the current controls.', 'Use wait if the element is still loading.'],
    'NOT_UNIQUE': ['Inspect locate candidates and narrow role/name/label or select one returned ref.'],
    'STALE_REFERENCE': ['Read or locate the current document and obtain a new ref.'],
    'COVERED': ['Inspect the page or screenshot for an overlay.', 'Dismiss the overlay or scroll the target into view; do not bypass with force unless explicitly intended.'],
    'NOT_VISIBLE': ['Scroll the element into view or open the section containing it.', 'Wait until visible, then inspect before retrying.'],
    'DISABLED': ['Inspect the control and complete prerequisites; wait until enabled.'],
    'READ_ONLY': ['Find the editable control or use the page’s edit action.'],
    'TIMEOUT': ['Read the current page state and inspect frames or selectors.', 'Increase the element wait only if the page is still loading.'],
    'INVALID_SELECTOR': ['Use a valid CSS selector or role/name/label/ref from locate.'],
    'INVALID_ARGUMENT': ['Check capabilities and tool argument schema.'],
    'INVALID_VALUE': ['Inspect the input type or select options and provide an accepted value.'],
    'ENGINE_VERSION_MISMATCH': ['Reload the tab and update the extension if needed.'],
    'DEVICE_OFFLINE': ['Open Firefox on Android and enable Browser Bridge.', 'Check the selected device, reachable broker address and network.'],
    'UNAUTHORIZED': ['Check device pairing and broker credentials; pair again only after revocation if needed.'],
    'COMMAND_TIMEOUT': ['Inspect current page state before repeating any action.', 'The action may already have occurred; do not retry blindly.'],
    'NETWORK_ERROR': ['Check broker availability and network.', 'Inspect current page state before repeating an action; delivery may have occurred.'],
}
PRECONDITION_CODES = set(REMEDIES) - {'TIMEOUT','COMMAND_TIMEOUT','NETWORK_ERROR','PAGE_RESPONSE_TIMEOUT','CANCELED','INVALID_VALUE','NAVIGATION_TIMEOUT','VIEWPORT_MEASUREMENT_UNAVAILABLE','ACTION_UNCERTAIN','LEASE_EXPIRED'}

def failure(error, device=None, operation=None):
    message=str(error)
    match=re.match(r'^([A-Z][A-Z_]+):', message)
    code=match.group(1) if match else 'ACTION_ERROR'
    if 'Device offline' in message: code='DEVICE_OFFLINE'
    elif 'Missing host permission' in message: code='HOST_PERMISSION_REQUIRED'
    elif 'Unauthorized' in message: code='UNAUTHORIZED'
    elif 'Timed out; execution may have occurred' in message: code='COMMAND_TIMEOUT'
    elif isinstance(error,(OSError,ConnectionError)): code='NETWORK_ERROR'
    result={'code':code,'message':message,'operation':operation,'device':device,
        'actionMayHaveOccurred':code not in PRECONDITION_CODES and operation not in {'tabs','read','inspect','locate','capabilities','frames','screenshot','wait'},
        'retryableAfterRecovery':code in REMEDIES and code not in {'COMMAND_TIMEOUT','NETWORK_ERROR','PAGE_RESPONSE_TIMEOUT','NAVIGATION_TIMEOUT','VIEWPORT_MEASUREMENT_UNAVAILABLE','ACTION_UNCERTAIN','LEASE_EXPIRED','HOST_PERMISSION_REQUIRED'},
        'nextSteps':REMEDIES.get(code,['Inspect the current page and capabilities before deciding whether to repeat the operation.'])}
    command=re.search(r'Command ID: ([a-zA-Z0-9_-]+)',message)
    if command:result['commandId']=command.group(1)
    action=re.search(r'Action ID: ([a-zA-Z0-9_-]+)',message)
    if action:result['actionId']=action.group(1)
    return result

def local_android_foreground(device, origin):
    package=os.environ.get('BROWSER_BRIDGE_ANDROID_PACKAGE')
    bound_device=os.environ.get('BROWSER_BRIDGE_ANDROID_DEVICE')
    if not package or device != bound_device:return {'available':False,'reason':'No local Android foreground helper configured for this device.'}
    if package not in {'org.mozilla.fenix','org.mozilla.firefox','org.mozilla.firefox_beta'}:
        raise ValueError('Unsupported local Firefox package')
    parts=urlsplit(origin)
    if parts.scheme not in {'http','https'} or parts.hostname not in {'127.0.0.1','localhost','::1'} or parts.username or parts.password:
        raise ValueError('Local Android helper requires a loopback broker URL')
    executable=Path('/data/data/com.termux/files/usr/bin/am')
    if not executable.is_file():return {'available':False,'reason':'The Linux host has no local Android activity launcher.'}
    response=subprocess.run([str(executable),'start','--user','0','-a','android.intent.action.VIEW','-d',origin.rstrip('/')+'/health','-p',package],capture_output=True,text=True,timeout=10)
    combined=response.stdout+response.stderr
    if response.returncode or 'Error:' in combined:raise RuntimeError('ANDROID_FOREGROUND_FAILED: Android did not accept the Firefox launch; open Firefox manually.')
    return {'available':True,'launchRequested':True,'package':package,'verifiedVisible':False}
