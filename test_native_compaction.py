import unittest
from unittest.mock import patch

import mcp_server
from response_policy import native_elements, project_response

SEARCH = {"role": "button", "accessibleName": "Search"}


def element(ref, x, y, w, h, **fields):
    return {"ref": ref, "rect": {"x": x, "y": y, "width": w, "height": h}, **SEARCH, **fields}


class NativeCompactionTest(unittest.TestCase):
    def test_drops_duplicates_nested_copies_and_merged_containers(self):
        elements = [
            {"ref": "page", "role": "button", "accessibleName": "Main menu Search Help User settings Unread messages", "rect": {"x": 0, "y": 0, "width": 1600, "height": 2000}},
            element("outer", 2638, 441, 113, 124),
            element("inner", 2640, 443, 109, 120),
            element("copy", 2640, 443, 109, 120),
            {"ref": "help", "role": "button", "accessibleName": "Help", "rect": {"x": 2751, "y": 441, "width": 125, "height": 125}},
        ]
        kept, omitted = native_elements(elements)
        self.assertEqual([e["ref"] for e in kept], ["inner", "help"])
        self.assertEqual(omitted, 3)

    def test_compact_native_read_and_verified_write(self):
        read = project_response("read", {"backend": "android-accessibility", "elements": [element("a", 1, 1, 5, 5, value=None), element("b", 1, 1, 5, 5)]}, "compact")
        self.assertEqual(read["elements"], [{"ref": "a", "role": "button", "accessibleName": "Search"}])
        self.assertEqual(read["duplicatesOmitted"], 1)
        click = project_response("click", {"executed": True, "verified": True, "effect": "screen_changed", "method": "screen_tap",
                                           "resolvedAncestor": False, "ancestorDepth": 0, "verification": {"delayMs": 500}, "nextSteps": ["Read the app only if needed"]}, "compact")
        self.assertEqual(click, {"executed": True, "verified": True, "effect": "screen_changed", "method": "screen_tap"})
        failed = {"executed": True, "verified": False, "verification": {}, "nextSteps": ["Read the app before repeating"]}
        self.assertEqual(project_response("click", failed, "compact"), failed)


class NativeResolveTest(unittest.TestCase):
    def test_click_by_name_acts_on_the_single_match_and_retries_stale_refs(self):
        calls = []
        replies = iter([
            {"package": "p.app", "elements": [element("r1", 0, 0, 10, 10)]},
            {"error": {"code": "STALE_REFERENCE"}},
            {"package": "p.app", "elements": [element("r2", 0, 0, 10, 10), element("r2b", 0, 0, 10, 10)]},
            {"executed": True},
        ])
        def fake(url, token, device, operation, values):
            calls.append((operation, values)); return next(replies)
        with patch.object(mcp_server, "execute_browser_command", fake):
            result = mcp_server.resolve_native_target("u", "t", "d", "click", {"package": "p.app", "name": "Search", "role": "button", "force": True})
        self.assertEqual(result, {"executed": True})
        self.assertEqual(calls[1], ("click", {"package": "p.app", "force": True, "ref": "r1"}))
        self.assertEqual(calls[3], ("click", {"package": "p.app", "force": True, "ref": "r2"}))

    def test_ambiguous_or_missing_names_fall_back_to_the_companion(self):
        calls = []
        replies = iter([{"package": "p.app", "elements": []}, {"error": {"code": "TARGET_NOT_FOUND"}}])
        def fake(url, token, device, operation, values):
            calls.append(operation); return next(replies)
        with patch.object(mcp_server, "execute_browser_command", fake):
            result = mcp_server.resolve_native_target("u", "t", "d", "click", {"package": "p.app", "name": "Missing"})
        self.assertEqual(result["error"]["code"], "TARGET_NOT_FOUND")
        self.assertEqual(calls, ["locate", "click"])
        self.assertFalse(mcp_server.native_by_name("click", {"package": "p.app", "ref": "x", "name": "y"}))
        self.assertFalse(mcp_server.native_by_name("click", {"tabId": 1, "name": "y"}))


if __name__ == "__main__":
    unittest.main()
