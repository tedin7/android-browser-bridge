"""Verify fixed browser navigations using document snapshots, including Android BFCache.

The dispatcher accepts (operation, arguments) and returns its raw result. It must
bound its own transport requests: this module cannot cancel an in-flight call.
Navigation is sent once; subsequent calls are read-only snapshots.
"""

import math
import time


NAVIGATION_OPERATIONS = frozenset({"open", "navigate", "back", "forward", "reload"})


class NavigationError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def _snapshot_args(args, tab_id=None):
    result = {"text": False, "maxElements": 0, "selectors": False}
    if tab_id is not None:
        result["tabId"] = tab_id
    elif args.get("tabId") is not None:
        result["tabId"] = args["tabId"]
    return result


def _http_snapshot(value):
    return isinstance(value, dict) and isinstance(value.get("url"), str) and value["url"].lower().startswith(("http://", "https://"))


def execute_navigation(dispatch, op, args):
    """Dispatch once and prove a completed document/URL transition through read.

    Other operations and navigations without waitUntil='complete' pass through.
    For existing HTTP pages, a readable pre-navigation snapshot is required.
    Navigating from a protected non-HTTP page is permitted when the pre-read
    explicitly reports that HTTP(S) page URLs are required.
    """
    args = dict(args or {})
    if op not in NAVIGATION_OPERATIONS or args.get("waitUntil") != "complete":
        return dispatch(op, args)

    timeout_ms = args.get("timeoutMs", 10000)
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, (int, float)) or not math.isfinite(timeout_ms):
        raise ValueError("timeoutMs must be a finite number")
    timeout = min(15000, max(0, timeout_ms)) / 1000
    previous = None
    protected_previous = False
    if op != "open":
        try:
            previous = dispatch("read", _snapshot_args(args))
        except Exception as error:
            message = str(error)
            protected_previous = op == "navigate" and ("Only HTTP(S) page URLs allowed" in message or "Only HTTP page URLs allowed" in message)
            if not protected_previous:
                raise NavigationError("NAVIGATION_PRECONDITION", "The current page could not be read. Run foreground for this tab, open Firefox on Android, and verify read before navigating.") from error
        if not protected_previous and not _http_snapshot(previous):
            raise NavigationError("NAVIGATION_PRECONDITION", "A readable HTTP(S) page snapshot is required. Run foreground for this tab and verify read before navigating.")

    command_args = {**args, "waitUntil": "none"}
    result = dispatch(op, command_args)
    # The deadline bounds completion verification, rather than treating the
    # duration of the single navigation submission as permission to replay it.
    deadline = time.monotonic() + timeout
    tab_id = result.get("id", result.get("tabId")) if isinstance(result, dict) else None
    if tab_id is None:
        tab_id = args.get("tabId")
    read_args = _snapshot_args(args, tab_id)
    interval = 0.025
    while True:
        try:
            current = dispatch("read", read_args)
        except Exception:
            # Document replacement can transiently remove the message handler.
            # Only the fixed read is repeated, never the navigation itself.
            current = None
        if _http_snapshot(current) and current.get("readyState") == "complete":
            changed = op == "open" or protected_previous
            if previous is not None:
                changed = current["url"] != previous["url"] or (
                    bool(previous.get("documentId")) and bool(current.get("documentId"))
                    and current["documentId"] != previous["documentId"]
                )
            if changed:
                return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NavigationError("NAVIGATION_TIMEOUT", "Navigation was submitted once, but its completed document transition could not be verified. It may still complete; do not repeat it automatically. Run foreground for this tab and inspect its state.")
        time.sleep(min(interval, remaining))
        interval = min(0.1, interval * 1.5)
