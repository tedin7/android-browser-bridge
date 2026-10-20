"""Lean MCP responses; raw broker results and navigation evidence stay untouched."""
import base64
import binascii
from urllib.parse import urlsplit, urlunsplit

MODES = frozenset({"compact", "full", "fields"})
PROTECTED = frozenset({
    "id", "tabId", "frameId", "parentFrameId", "device", "operation", "url",
    "documentId", "readyState", "viewport", "scroll", "before", "after", "window",
    "backend", "package", "complete", "textLengthExact", "elementsComplete", "elementCount", "count", "returned", "truncated", "nextOffset", "textLength", "textTruncated",
    "offset", "textOffset", "nextTextOffset", "state", "status", "completed", "results",
    "error", "code", "message", "nextSteps", "nextStep", "commandId", "actionId", "timing",
    "actionMayHaveOccurred", "retryableAfterRecovery", "localAndroid", "navigation",
    "verified", "verifiedVisible", "androidOSForegroundGuaranteed", "tabActivated",
    "windowFocusSupported", "windowFocusRequested", "windowFocused", "windowFocusError",
    "requested", "actual", "matched", "attempts", "desktopOnly", "affectsWindowTabs", "windowId", "mimeType", "imageIndex", "ok", "trustedEvents", "effect", "hint", "container", "duplicatesOmitted", "urlQueryOmitted", "urlTruncated", "ref", "nameTruncated", "hrefTruncated",
})
RESULT_FIELDS = PROTECTED | frozenset({
    "text", "title", "elements", "ref", "tag", "role", "accessibleName", "name", "type", "href",
    "checked", "enabled", "visible", "rect", "selector", "value", "readOnly", "focused", "options",
    "values", "length", "durationMs", "key", "location", "x", "y", "from", "to", "steps", "active", "version", "operations",
    "transport", "frames", "screenshot", "openShadowRoots", "closedShadowRoots", "nativeAndroidUI",
    "foregroundAPI", "parallelTabs", "maxParallelCommands", "layout", "desktopViewport",
})


def response_options(arguments, *, tool="browser_command"):
    """Validate before any browser action, including fields unavailable to this API."""
    allowed = {"device", "op", "args", "resultMode", "resultFields"} if tool == "browser_command" else {"id", "actionId", "waitMs", "resultMode", "resultFields"}
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError("INVALID_ARGUMENT: Unknown " + tool + " argument")
    mode = arguments.get("resultMode", "compact")
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("INVALID_ARGUMENT: resultMode must be compact, full or fields")
    fields = arguments.get("resultFields")
    if mode == "fields":
        if not isinstance(fields, list) or not 1 <= len(fields) <= 32 or any(not isinstance(field, str) or field not in RESULT_FIELDS for field in fields):
            raise ValueError("INVALID_ARGUMENT: fields mode requires 1–32 known resultFields")
        fields = frozenset(fields)
    elif fields is not None:
        raise ValueError("INVALID_ARGUMENT: resultFields requires resultMode fields")
    return mode, fields


def prepare_arguments(operation, arguments, mode):
    """Only supply missing lean defaults. Explicit limits and full mode win."""
    if not isinstance(arguments, dict):
        raise ValueError("INVALID_ARGUMENT: args must be an object")
    values = dict(arguments)
    if mode != "full":
        if operation == "read":
            values.setdefault("textLimit", 2000)
            values.setdefault("maxElements", 20)
            values.setdefault("selectors", False)
            values.setdefault("responseFields", ["accessibleName", "name", "type", "href", "checked"] + (["selector"] if values.get("selectors") else []))
        elif operation == "locate":
            values.setdefault("maxElements", 20)
            values.setdefault("selectors", False)
            values.setdefault("responseFields", ["accessibleName", "name", "type", "href", "checked"] + (["selector"] if values.get("selectors") else []))
        elif operation == "batch" and isinstance(values.get("steps"), list):
            steps = []
            for step in values["steps"]:
                if not isinstance(step, dict):
                    raise ValueError("INVALID_ARGUMENT: Every batch step must be an object")
                steps.append({**step, "args": prepare_arguments(step.get("op"), step.get("args", {}), mode)})
            values["steps"] = steps
    return values


def _compact_element(element, arguments):
    if not isinstance(element, dict):
        return element
    result = dict(element)
    result.pop("rect", None)
    if arguments.get("selectors") is not True:
        result.pop("selector", None)
    for field in ("visible", "enabled"):
        if result.get(field) is True:
            result.pop(field)
    if result.get("accessibleName") == result.get("text"):
        result.pop("text", None)
    if result.get("name") == element.get("text"):
        result.pop("name", None)
    for field in ("name", "href"):
        if isinstance(result.get(field), str) and len(result[field]) > 512:
            result[field] = result[field][:512]
            result[field + "Truncated"] = True
    return result


def native_elements(elements):
    """Firefox exposes every container as a button whose name concatenates its children and
    repeats nodes with identical bounds. Keep one per (role, name, bounds) and drop large
    containers with merged names: they cost tokens and make name lookups ambiguous."""
    def area(element):
        rect = element.get("rect") or {}
        return max(0, rect.get("width", 0)) * max(0, rect.get("height", 0))
    largest = max((area(e) for e in elements if isinstance(e, dict)), default=0)
    kept, seen, omitted = [], set(), 0
    for element in elements:
        if not isinstance(element, dict):
            kept.append(element); continue
        rect = element.get("rect") or {}
        key = (element.get("role"), element.get("accessibleName"), tuple(rect.get(k) for k in ("x", "y", "width", "height")))
        name = element.get("accessibleName") or ""
        container = len(name) > 40 and largest and area(element) >= 0.25 * largest
        if key in seen or container:
            omitted += 1; continue
        seen.add(key); kept.append(element)
    # Same role and name nested inside each other: keep the innermost node.
    def inside(inner, outer):
        a, b = inner.get("rect") or {}, outer.get("rect") or {}
        return all(k in a and k in b for k in ("x", "y", "width", "height")) and a["x"] >= b["x"] and a["y"] >= b["y"] and \
            a["x"] + a["width"] <= b["x"] + b["width"] and a["y"] + a["height"] <= b["y"] + b["height"]
    nested = {id(outer) for outer in kept if isinstance(outer, dict) for inner in kept
              if isinstance(inner, dict) and inner is not outer and inner.get("role") == outer.get("role")
              and inner.get("accessibleName") == outer.get("accessibleName") and inside(inner, outer) and area(inner) < area(outer)}
    omitted += len(nested)
    return [element for element in kept if id(element) not in nested], omitted


def _select_fields(value, fields):
    required = PROTECTED | fields
    return {key: item for key, item in value.items() if key in required or (key in {"visible", "enabled"} and item is False) or (key == "readOnly" and item is True)}


def project_response(operation, result, mode, fields=None, arguments=None):
    """Preserve all error and execution evidence; never alter broker-owned data."""
    arguments = arguments or {}
    if mode == "full":
        return result
    if operation == "frames" and isinstance(result, list):
        frames = []
        for frame in result:
            if not isinstance(frame, dict) or not isinstance(frame.get("url"), str):
                frames.append(frame); continue
            normalized = dict(frame)
            try:
                parts = urlsplit(frame["url"])
                normalized["url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                if parts.query or parts.fragment:
                    normalized["urlQueryOmitted"] = True
            except ValueError:
                # This is descriptive browser data, never a URL to navigate.
                normalized["url"] = frame["url"].split("?", 1)[0].split("#", 1)[0]
                if normalized["url"] != frame["url"]:
                    normalized["urlQueryOmitted"] = True
            if len(normalized["url"]) > 512:
                normalized["url"] = normalized["url"][:512]
                normalized["urlTruncated"] = True
            frames.append(normalized)
        return [_select_fields(frame, fields) if isinstance(frame, dict) else frame for frame in frames] if mode == "fields" else frames
    if operation == "batch" and isinstance(result, dict):
        projected = dict(result)
        steps = arguments.get("steps", [])
        projected["results"] = [
            {**entry, "result": project_response(entry.get("op"), entry["result"], mode, fields,
                steps[index].get("args", {}) if index < len(steps) and isinstance(steps[index], dict) else {})}
            if isinstance(entry, dict) and "result" in entry and not entry.get("error") else entry
            for index, entry in enumerate(result.get("results", []))
        ]
        return _select_fields(projected, fields) if mode == "fields" else projected
    if mode == "fields" and isinstance(result, list):
        return [_select_fields(entry, fields) if isinstance(entry, dict) and not entry.get("error") and not entry.get("nextSteps") else entry for entry in result]
    if not isinstance(result, dict) or result.get("error"):
        return result
    if result.get("nextSteps") and not (result.get("verified") is True and isinstance(result.get("verification"), dict)):
        return result
    projected = dict(result)
    if isinstance(result.get("verification"), dict) and result.get("verified") is True:
        # A verified native write needs no method notes or follow-up advice.
        for key in ("verification", "nextSteps"):
            projected.pop(key, None)
        if result.get("resolvedAncestor") is False and result.get("ancestorDepth") == 0:
            projected.pop("resolvedAncestor", None); projected.pop("ancestorDepth", None)
    if operation == "wait" and isinstance(result.get("element"), dict):
        projected["element"] = {key: result["element"][key] for key in ("ref", "tag", "role", "accessibleName") if key in result["element"]}
    if isinstance(result.get("viewport"), dict):
        # Width/height/visibility answer "is the page suspended?"; zoom internals cost every turn.
        projected["viewport"] = {key: result["viewport"][key] for key in ("width", "height", "visibility") if key in result["viewport"]}
    if operation in {"read", "locate"} and isinstance(result.get("elements"), list):
        elements, omitted = result["elements"], 0
        if result.get("backend") == "android-accessibility" or "package" in result:
            elements, omitted = native_elements(elements)
            if omitted:
                projected["duplicatesOmitted"] = omitted
        projected["elements"] = [{key: value for key, value in _compact_element(element, arguments).items() if value is not None}
                                 if isinstance(element, dict) else element for element in elements]
        if operation == "locate":
            returned = len(projected["elements"])
            projected["returned"] = returned
            projected["truncated"] = isinstance(result.get("count"), int) and result["count"] > returned + omitted
    if mode == "fields":
        return _select_fields(projected, fields)
    return projected


def image_content(operation, result):
    """Lift fixed screenshot results, including batch steps, out of text JSON."""
    images = []
    def visit(op, value):
        if op == "screenshot" and isinstance(value, dict) and "data" in value:
            data, mime = value["data"], value.get("mimeType")
            if mime not in {"image/png", "image/jpeg"} or not isinstance(data, str) or not data or len(data) > 16 * 1024 * 1024:
                raise ValueError("INVALID_RESULT: Screenshot format is invalid")
            try:
                base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError("INVALID_RESULT: Screenshot encoding is invalid") from None
            index = len(images)
            images.append({"type": "image", "data": data, "mimeType": mime})
            return {**{key: item for key, item in value.items() if key != "data"}, "imageIndex": index}
        if op == "batch" and isinstance(value, dict) and isinstance(value.get("results"), list):
            return {**value, "results": [
                {**entry, "result": visit(entry.get("op"), entry["result"])}
                if isinstance(entry, dict) and "result" in entry else entry
                for entry in value["results"]
            ]}
        return value
    metadata = visit(operation, result)
    return images, metadata


def serialize_result(operation, result, mode="compact", fields=None, arguments=None, envelope=None):
    """One multimodal representation for immediate results and recovered receipts."""
    import json
    images, metadata = image_content(operation, result)
    projected = project_response(operation, metadata, mode, fields, arguments)
    if envelope is not None:
        projected = {**envelope, "result": projected}
    return {"content": [*images, {"type": "text", "text": json.dumps(projected, ensure_ascii=False, separators=(",", ":"))}]}
