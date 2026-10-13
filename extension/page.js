/* Resident fixed-operation engine. No remotely supplied scripts or expressions. */
(() => {
  if (globalThis.__browserBridgePageVersion === "1.0.3") return;
  if (globalThis.__browserBridgePageListener) browser.runtime.onMessage.removeListener(globalThis.__browserBridgePageListener);
  const engineVersion = "1.0.3";
  globalThis.__browserBridgePageVersion = engineVersion;
  const epoch = Math.random().toString(36).slice(2, 10);
  let nextRef = 0;
  const identities = new WeakMap(), references = new Map();
  const pageOps = new Set(["read", "inspect", "locate", "click", "double_click", "hover", "focus", "fill", "type", "clear", "select", "check", "press", "scroll", "wait", "click_point", "drag", "webmcp_discover", "webmcp_invoke"]);
  function fail(code, message) { const error = Error(message); error.code = code; throw error; }
  function reference(el, observedName) {
    let ref = identities.get(el);
    if (!ref) { ref = epoch + "-e" + ++nextRef; identities.set(el, ref); }
    if (!references.has(ref) || observedName !== undefined) references.set(ref, {node: new WeakRef(el), role: roleOf(el), type: el.type, name: observedName});
    if (references.size > 4096) references.delete(references.keys().next().value);
    return ref;
  }
  function normalized(value) { return String(value || "").replace(/\s+/g, " ").trim(); }
  function roleOf(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit.trim().split(/\s+/)[0];
    const tag = el.tagName.toLowerCase(), type = el.type;
    if (tag === "button" || (tag === "input" && ["button", "submit", "reset", "image"].includes(type))) return "button";
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "textarea") return "textbox";
    if (tag === "input") return ({checkbox: "checkbox", radio: "radio", range: "slider", number: "spinbutton", search: "searchbox"})[type] || (!["hidden", "file", "color"].includes(type) ? "textbox" : null);
    if (tag === "select") return el.multiple || el.size > 1 ? "listbox" : "combobox";
    if (tag === "option") return "option";
    if (/^h[1-6]$/.test(tag)) return "heading";
    return ({img: "img", summary: "button", progress: "progressbar", meter: "meter", table: "table", tr: "row", td: "cell", th: "columnheader", dialog: "dialog"})[tag] || (el.isContentEditable ? "textbox" : null);
  }
  function labelOf(el) { return normalized(el.labels ? [...el.labels].map(label => label.textContent).join(" ") : ""); }
  function accessibleName(el) {
    const labelled = el.getAttribute("aria-labelledby"), root = el.getRootNode();
    if (labelled) {
      const text = normalized(labelled.split(/\s+/).map(id => root.getElementById?.(id)?.textContent || "").join(" "));
      if (text) return text;
    }
    const aria = el.getAttribute("aria-label");
    if (aria) return normalized(aria);
    const label = labelOf(el); if (label) return label;
    if (el.tagName === "IMG" || el.type === "image") return normalized(el.getAttribute("alt") || el.title);
    if (el.tagName === "INPUT" && ["button", "submit", "reset"].includes(el.type)) return normalized(el.value || (el.type === "submit" ? "Submit" : el.type === "reset" ? "Reset" : ""));
    return normalized(el.innerText || el.textContent || el.title || el.getAttribute("placeholder"));
  }
  function allElements(root = document) {
    const result = [], roots = [root];
    for (let i = 0; i < roots.length; i++) {
      for (const el of roots[i].querySelectorAll("*")) {
        result.push(el);
        if (el.shadowRoot) roots.push(el.shadowRoot);
      }
    }
    return result;
  }
  function semanticArgs(args) { return ["role", "name", "label", "testId", "textQuery"].some(key => typeof args[key] === "string") || typeof args.text === "string"; }
  function find(args) {
    let elements;
    if (args.ref) {
      const previous = references.get(args.ref);
      const el = previous?.node.deref();
      if (!el || !el.isConnected) fail("STALE_REFERENCE", "Element reference is stale; read or locate the page again");
      if (roleOf(el) !== previous.role || el.type !== previous.type || (previous.name !== undefined && accessibleName(el).slice(0, 180) !== previous.name)) fail("STALE_REFERENCE", "Observed target semantics changed; locate and confirm the current control again");
      elements = [el];
    } else if (typeof args.selector === "string" && args.selector.trim()) {
      const parts = args.selector.split(/\s*>>>\s*/);
      let roots = [document];
      try {
        for (let i = 0; i < parts.length; i++) {
          elements = roots.flatMap(root => [...root.querySelectorAll(parts[i])]);
          if (i < parts.length - 1) roots = elements.map(el => el.shadowRoot).filter(Boolean);
        }
      } catch (_) { fail("INVALID_SELECTOR", "Invalid CSS selector"); }
    } else if (semanticArgs(args)) elements = allElements();
    else fail("INVALID_SELECTOR", "Provide selector, ref, role, name, label, testId or textQuery");
    if (!semanticArgs(args)) return elements;
    const match = (actual, requested) => typeof requested !== "string" || (args.exact === false ? normalized(actual).toLocaleLowerCase().includes(normalized(requested).toLocaleLowerCase()) : normalized(actual) === normalized(requested));
    const text = args.textQuery ?? (typeof args.text === "string" ? args.text : undefined);
    elements = elements.filter(el => (!args.name || roleOf(el) || el.hasAttribute("aria-label") || el.hasAttribute("aria-labelledby") || el.labels?.length) && match(roleOf(el), args.role) && match(accessibleName(el), args.name) && match(labelOf(el), args.label) && match(el.getAttribute("data-testid") || el.getAttribute("data-test-id") || el.getAttribute("data-test"), args.testId) && match(el.innerText || el.textContent, text));
    // Text-only queries select the deepest matching node rather than every containing ancestor.
    if (typeof text === "string" && !args.role && !args.name && !args.label && !args.testId && !args.selector && !args.ref) {
      const matches = new Set(elements);
      const ancestors = new Set();
      for (const el of elements) for (let parent = el.parentElement || el.getRootNode().host; parent; parent = parent.parentElement || parent.getRootNode().host) if (matches.has(parent)) ancestors.add(parent);
      elements = elements.filter(el => !ancestors.has(el));
      elements = [...new Set(elements.map(el => el.closest("button,a[href],[role=button],[role=link],summary") || el))];
    }
    return args.includeHidden ? elements : elements.filter(visible);
  }
  function one(args) {
    const matches = find(args);
    if (!matches.length) fail("NOT_FOUND", "No element matches; use wait or read first");
    if (matches.length !== 1) fail("NOT_UNIQUE", `Selector must match one element; matched ${matches.length}`);
    return matches[0];
  }
  function visible(el, measuredRect = null) {
    const style = getComputedStyle(el), rect = measuredRect && typeof measuredRect === "object" ? measuredRect : el.getBoundingClientRect();
    return el.isConnected && style.display !== "none" && style.visibility !== "hidden" && style.visibility !== "collapse" && rect.width > 0 && rect.height > 0;
  }
  function enabled(el) { return !el.matches(":disabled") && el.getAttribute("aria-disabled") !== "true"; }
  function actionable(el, args, editing = false) {
    if (!el.isConnected) fail("STALE_REFERENCE", "Element detached from document");
    if (!enabled(el)) fail("DISABLED", "Element is disabled");
    if (editing && el.readOnly) fail("READ_ONLY", "Element is read-only");
    if (!args.force && !visible(el)) fail("NOT_VISIBLE", "Element is not visible");
  }
  function selectorFor(element, siblingCache) {
    const root = element.getRootNode(), parts = [];
    for (let el = element; el && el.nodeType === 1; el = el.parentElement) {
      if (el.id && root.querySelectorAll("#" + CSS.escape(el.id)).length === 1) {
        parts.unshift("#" + CSS.escape(el.id)); break;
      }
      let suffix = "";
      if (el.parentElement) {
        let entries = siblingCache.get(el.parentElement);
        if (!entries) {
          entries = new Map(); const counts = new Map();
          for (const child of el.parentElement.children) {
            const count = (counts.get(child.tagName) || 0) + 1; counts.set(child.tagName, count);
            entries.set(child, count);
          }
          siblingCache.set(el.parentElement, entries);
        }
        suffix = `:nth-of-type(${entries.get(el)})`;
      }
      parts.unshift(el.tagName.toLowerCase() + suffix);
    }
    const own = parts.join(" > ");
    return root.host ? selectorFor(root.host, siblingCache) + " >>> " + own : own;
  }
  const descriptorFields = new Set(["ref", "tag", "role", "accessibleName", "text", "visible", "enabled", "rect", "selector", "type", "name", "href", "checked", "options"]);
  function selectedResponseFields(args) {
    if (args.responseFields === undefined) return null;
    if (!Array.isArray(args.responseFields) || args.responseFields.length > descriptorFields.size || args.responseFields.some(field => typeof field !== "string" || !descriptorFields.has(field))) fail("INVALID_ARGUMENT", "responseFields must contain known element descriptor fields");
    return new Set(args.responseFields);
  }
  function describe(el, cache = new WeakMap(), selectors = true, fields = null) {
    const wants = field => fields === null || fields.has(field);
    const rect = el.getBoundingClientRect();
    const observedName = wants("accessibleName") ? accessibleName(el).slice(0, 180) : undefined;
    const result = {ref: reference(el, observedName), tag: el.tagName.toLowerCase(), role: roleOf(el), visible: visible(el, rect), enabled: enabled(el)};
    if (wants("accessibleName")) result.accessibleName = observedName;
    if (wants("text")) {
      const label = el.getAttribute("aria-label") || (el.labels ? [...el.labels].map(label => label.textContent).join(" ") : "");
      result.text = (label || el.innerText || "").trim().slice(0, 180);
    }
    if (wants("rect")) result.rect = {x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height)};
    if (selectors && wants("selector")) result.selector = selectorFor(el, cache);
    if (wants("type") && el.type) result.type = el.type;
    if (wants("name") && el.name) result.name = el.name;
    if (wants("href") && el.href) result.href = el.getAttribute("href");
    if (wants("checked") && typeof el.checked === "boolean") result.checked = el.checked;
    // Select options travel with the control (requested via type or options) so agents need no extra inspect turn.
    if (el.tagName === "SELECT" && el.options && (wants("type") || (fields !== null && fields.has("options")))) {
      const options = [...el.options];
      result.options = options.slice(0, 25).map(option => {
        const text = option.text.trim().slice(0, 80);
        return text === option.value && !option.disabled && !option.selected ? option.value : {value: option.value, ...(text !== option.value ? {text} : {}), ...(option.selected ? {selected: true} : {}), ...(option.disabled ? {disabled: true} : {})};
      });
      if (options.length > 25) result.optionsTruncated = true;
    }
    return result;
  }
  function viewportInfo() {
    const visual = window.visualViewport;
    return {width: innerWidth, height: innerHeight, documentWidth: document.documentElement.getBoundingClientRect().width, visibility: document.visibilityState,
      visual: visual ? {width: visual.width, height: visual.height, offsetLeft: visual.offsetLeft, offsetTop: visual.offsetTop, scale: visual.scale} : null};
  }
  function layoutInfo(el) {
    const style = getComputedStyle(el), rect = el.getBoundingClientRect(), visual = window.visualViewport;
    const left = visual?.offsetLeft || 0, top = visual?.offsetTop || 0;
    const right = left + (visual?.width ?? innerWidth), bottom = top + (visual?.height ?? innerHeight);
    const rendered = visible(el), x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
    const inViewport = rendered && rect.right > left && rect.bottom > top && rect.left < right && rect.top < bottom;
    const centerInViewport = rendered && x >= left && y >= top && x < right && y < bottom;
    const hit = centerInViewport ? hitAt({clientX: x, clientY: y}) : null;
    const hitTest = !!hit && composedContains(el, hit);
    return {
      position: style.position, top: style.top, right: style.right, bottom: style.bottom, left: style.left,
      zIndex: style.zIndex, display: style.display, overflowX: style.overflowX, overflowY: style.overflowY,
      clientWidth: el.clientWidth, clientHeight: el.clientHeight, scrollWidth: el.scrollWidth, scrollHeight: el.scrollHeight,
      inViewport, centerInViewport, hitTest, hitTestPerformed: centerInViewport, occluded: hit ? !hitTest : null
    };
  }
  function position(target) {
    const windowTarget = target === window, element = document.scrollingElement;
    return {x: windowTarget ? scrollX : target.scrollLeft, y: windowTarget ? scrollY : target.scrollTop,
      maxX: Math.max(0, (windowTarget ? element.scrollWidth - innerWidth : target.scrollWidth - target.clientWidth)),
      maxY: Math.max(0, (windowTarget ? element.scrollHeight - innerHeight : target.scrollHeight - target.clientHeight))};
  }
  function setText(el, value, inputType = "insertText") {
    const event = new InputEvent("beforeinput", {bubbles: true, cancelable: true, inputType, data: value});
    if (!el.dispatchEvent(event)) fail("CANCELED", "Page canceled the input action");
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      const proto = el instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
      if (el.value !== value) fail("INVALID_VALUE", "Browser rejected this value for the input type");
    } else if (el.isContentEditable) el.textContent = value;
    else fail("NOT_EDITABLE", "Use input, textarea, or contenteditable");
    el.dispatchEvent(new InputEvent("input", {bubbles: true, inputType, data: value}));
  }
  function editableText(el) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return el.value;
    if (el.isContentEditable) return el.textContent;
    fail("NOT_EDITABLE", "Element does not support text editing");
  }
  function insertText(el, text, inputType = "insertText") {
    if (el.isContentEditable) {
      const selection = el.getRootNode().getSelection?.() || window.getSelection();
      let range = selection?.rangeCount ? selection.getRangeAt(0) : null;
      if (!range || !el.contains(range.commonAncestorContainer)) { range = document.createRange(); range.selectNodeContents(el); range.collapse(false); }
      if (!el.dispatchEvent(new InputEvent("beforeinput", {bubbles: true, cancelable: true, inputType, data: text}))) fail("CANCELED", "Page canceled the input action");
      range.deleteContents(); const node = document.createTextNode(text); range.insertNode(node); range.setStartAfter(node); range.collapse(true);
      selection?.removeAllRanges(); selection?.addRange(range);
      el.dispatchEvent(new InputEvent("input", {bubbles: true, inputType, data: text})); return;
    }
    const value = editableText(el), start = el.selectionStart ?? value.length, end = el.selectionEnd ?? value.length;
    setText(el, value.slice(0, start) + text + value.slice(end), inputType);
    if (typeof el.setSelectionRange === "function" && el.selectionStart !== null) el.setSelectionRange(start + text.length, start + text.length);
  }
  function viewportBounds() {
    const visual = window.visualViewport;
    const width = visual?.width ?? innerWidth, height = visual?.height ?? innerHeight;
    if (!(width > 0 && height > 0 && document.documentElement.getBoundingClientRect().width > 0)) fail("VIEWPORT_UNAVAILABLE", "This page has no rendered viewport; bring Firefox and this tab to the foreground, then retry");
    return {left: visual?.offsetLeft || 0, top: visual?.offsetTop || 0, right: (visual?.offsetLeft || 0) + width, bottom: (visual?.offsetTop || 0) + height};
  }
  function renderFrame() {
    return new Promise(resolve => {
      let frame, timer;
      const finish = () => { clearTimeout(timer); if (frame) cancelAnimationFrame(frame); resolve(); };
      frame = requestAnimationFrame(finish); timer = setTimeout(finish, 120);
    });
  }
  async function pointer(el, args) {
    actionable(el, args);
    let bounds = viewportBounds(), rect = el.getBoundingClientRect();
    const outside = rect.left < bounds.left || rect.top < bounds.top || rect.right > bounds.right || rect.bottom > bounds.bottom;
    if (outside) {
      const beforeX = scrollX, beforeY = scrollY, beforeRect = rect;
      el.scrollIntoView({block: "center", inline: "nearest", behavior: "instant"});
      rect = el.getBoundingClientRect();
      if (beforeX !== scrollX || beforeY !== scrollY || beforeRect.left !== rect.left || beforeRect.top !== rect.top) await renderFrame();
      actionable(el, args); bounds = viewportBounds(); rect = el.getBoundingClientRect();
    }
    let point, hit;
    for (let attempt = 0; attempt < 2; attempt++) {
      const left = Math.max(bounds.left, rect.left), top = Math.max(bounds.top, rect.top);
      const right = Math.min(bounds.right, rect.right), bottom = Math.min(bounds.bottom, rect.bottom);
      if (right <= left || bottom <= top) fail("NOT_VISIBLE", "Element does not intersect the rendered viewport");
      point = {clientX: (left + right) / 2, clientY: (top + bottom) / 2, bubbles: true, cancelable: true, view: window};
      hit = hitAt(point);
      if (hit || args.force || attempt === 1) break;
      await renderFrame(); bounds = viewportBounds(); rect = el.getBoundingClientRect();
    }
    if (!args.force && (!hit || !composedContains(el, hit))) fail("COVERED", hit ? "Element is covered by another element" : "The browser could not verify an actionable element at this point; bring Firefox and this tab to the foreground");
    return point;
  }
  async function mouseClick(el, args, detail) {
    const point = await pointer(el, args);
    el.dispatchEvent(new PointerEvent("pointerdown", {...point, pointerType: "mouse", pointerId: 1, buttons: 1}));
    const proceed = el.dispatchEvent(new MouseEvent("mousedown", {...point, buttons: 1, detail}));
    if (proceed) el.focus({preventScroll: true});
    el.dispatchEvent(new PointerEvent("pointerup", {...point, pointerType: "mouse", pointerId: 1}));
    el.dispatchEvent(new MouseEvent("mouseup", {...point, detail}));
    // HTMLElement.click applies native checkbox/radio defaults; event dispatch alone does not.
    el.click();
    return point;
  }
  function viewportPoint(x, y) {
    const bounds = viewportBounds();
    if (typeof x !== "number" || typeof y !== "number" || !Number.isFinite(x) || !Number.isFinite(y) || x < bounds.left || y < bounds.top || x >= bounds.right || y >= bounds.bottom) fail("INVALID_ARGUMENT", "Coordinates must be finite viewport CSS pixels within the visible page");
    return {clientX: x, clientY: y, bubbles: true, cancelable: true, view: window};
  }
  function hitAt(point) {
    let el = document.elementFromPoint(point.clientX, point.clientY);
    while (el?.shadowRoot?.elementFromPoint) {
      const inner = el.shadowRoot.elementFromPoint(point.clientX, point.clientY);
      if (!inner || inner === el) break;
      el = inner;
    }
    return el;
  }
  function composedContains(ancestor, child) {
    for (let node = child; node; node = node.parentElement || node.getRootNode().host) if (node === ancestor) return true;
    return false;
  }
  function dispatchPointer(el, name, point, buttons = 0) {
    return el.dispatchEvent(new PointerEvent(name, {...point, pointerType: "mouse", pointerId: 1, isPrimary: true, buttons, button: 0}));
  }
  async function coordinateAction(op, args) {
    const start = viewportPoint(args.x, args.y), hit = hitAt(start);
    if (!hit) fail("NOT_FOUND", "No page element at these coordinates");
    const el = args.selector || args.ref || semanticArgs(args) ? one(args) : hit;
    actionable(el, args);
    if (!args.force && !composedContains(el, hit)) fail("COVERED", "The requested element is not at these coordinates");
    const target = hit;
    for (let parent = target; parent; parent = parent.parentElement || parent.getRootNode().host) if (!enabled(parent)) fail("DISABLED", "Element or its containing control is disabled");
    let end, steps;
    if (op === "drag") {
      end = viewportPoint(args.toX, args.toY); steps = args.dragSteps ?? args.steps ?? 10;
      if (!Number.isInteger(steps) || steps < 1 || steps > 60) fail("INVALID_ARGUMENT", "Drag steps must be an integer from 1 to 60");
    }
    dispatchPointer(target, "pointermove", start);
    target.dispatchEvent(new MouseEvent("mousemove", start));
    const down = dispatchPointer(target, "pointerdown", start, 1);
    const mouseDown = target.dispatchEvent(new MouseEvent("mousedown", {...start, buttons: 1, detail: 1}));
    if (down && mouseDown) target.focus?.({preventScroll: true});
    if (op === "click_point") {
      dispatchPointer(target, "pointerup", start);
      target.dispatchEvent(new MouseEvent("mouseup", {...start, detail: 1}));
      // Dispatching click preserves point coordinates and browser activation behavior.
      target.dispatchEvent(new MouseEvent("click", {...start, detail: 1}));
      return {ok: true, ref: reference(target), x: start.clientX, y: start.clientY, trustedEvents: false};
    }
    for (let i = 1; i <= steps; i++) {
      const point = {...start, clientX: start.clientX + (end.clientX - start.clientX) * i / steps, clientY: start.clientY + (end.clientY - start.clientY) * i / steps};
      dispatchPointer(target, "pointermove", point, 1);
      target.dispatchEvent(new MouseEvent("mousemove", {...point, buttons: 1}));
    }
    // Native range widgets do not apply untrusted pointer defaults; update their fixed value explicitly.
    if (target instanceof HTMLInputElement && target.type === "range" && down && mouseDown) {
      const rect = target.getBoundingClientRect(), style = getComputedStyle(target);
      const vertical = style.writingMode.startsWith("vertical"), min = Number(target.min || 0), max = Number(target.max || 100);
      let ratio = vertical ? (end.clientY - rect.y) / rect.height : (end.clientX - rect.x) / rect.width;
      if (style.direction === "rtl") ratio = 1 - ratio;
      let value = min + Math.max(0, Math.min(1, ratio)) * (max - min);
      const step = target.step === "any" ? 0 : Number(target.step || 1);
      if (step > 0) value = min + Math.round((value - min) / step) * step;
      value = Number(Math.max(min, Math.min(max, value)).toPrecision(12));
      setText(target, String(value), "insertReplacementText");
      target.dispatchEvent(new Event("change", {bubbles: true}));
    }
    dispatchPointer(target, "pointerup", end);
    target.dispatchEvent(new MouseEvent("mouseup", {...end, detail: 1}));
    return {ok: true, ref: reference(target), from: {x: start.clientX, y: start.clientY}, to: {x: end.clientX, y: end.clientY}, steps, trustedEvents: false};
  }
  // Observable evidence after synthetic input; never a claim about application semantics.
  const stateAttributes = ["aria-expanded", "aria-checked", "aria-selected", "aria-pressed", "aria-activedescendant", "open"];
  const noChangeHint = "No observable change: this widget may ignore synthetic events. Do not repeat the same action; read to confirm, then use a native companion device (args.package) for a real tap if one is available.";
  function targetState(el) {
    const parts = [];
    for (let node = el, depth = 0; node?.nodeType === 1 && depth < 4; node = node.parentElement, depth++)
      for (const name of stateAttributes) if (node.hasAttribute(name)) parts.push(depth + name + "=" + node.getAttribute(name));
    if (typeof el.checked === "boolean") parts.push("checked=" + el.checked);
    if ("value" in el && typeof el.value === "string") parts.push("value=" + el.value);
    return parts.join("|");
  }
  // Apps rewrite their own URL encoding (%3A -> :) without navigating.
  function sameUrl(a, b) { try { return decodeURIComponent(a) === decodeURIComponent(b); } catch (_) { return a === b; } }
  function linked(a, b) { return composedContains(a, b) || composedContains(b, a); }
  async function observeEffect(el, action) {
    if (typeof MutationObserver !== "function" || typeof addEventListener !== "function") return action();
    const url = location.href, state = targetState(el);
    let changes = 0, leaving = false, wake = null;
    // The control's own focus, hover and ripple styling is not an effect of the action.
    const count = records => { for (const record of records) if (!(record.type === "attributes" && ["class", "style"].includes(record.attributeName) && (record.target === el || linked(el, record.target)))) changes++; };
    const observer = new MutationObserver(count);
    const leave = () => { leaving = true; wake?.(); };
    observer.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
    addEventListener("pagehide", leave); addEventListener("beforeunload", leave);
    try {
      const result = await action();
      const settle = delay => new Promise(resolve => { wake = resolve; if (leaving) resolve(); else setTimeout(resolve, delay); });
      await renderFrame(); count(observer.takeRecords());
      // Menus and dialogs often open after a short timer; wait a little longer only when nothing changed yet.
      if (!leaving && !changes && sameUrl(location.href, url) && targetState(el) === state) { await settle(200); count(observer.takeRecords()); }
      const effect = leaving || !sameUrl(location.href, url) ? "navigation" : !el.isConnected || targetState(el) !== state ? "target_state_changed" : changes ? "dom_changed" : "no_visible_change";
      return {...result, verified: effect !== "no_visible_change", effect, ...(effect === "no_visible_change" ? {hint: noChangeHint} : {})};
    } finally {
      observer.disconnect(); removeEventListener("pagehide", leave); removeEventListener("beforeunload", leave);
    }
  }
  function scrollable(node) {
    if (!(node instanceof Element) || (node.scrollHeight <= node.clientHeight + 1 && node.scrollWidth <= node.clientWidth + 1)) return false;
    const style = getComputedStyle(node);
    return /(auto|scroll|overlay)/.test(style.overflowY + " " + style.overflowX);
  }
  function scrollContainer(el) {
    for (let node = el.parentElement || el.getRootNode().host; node && node !== document.body && node !== document.documentElement; node = node.parentElement || node.getRootNode().host)
      if (scrollable(node)) return node;
    return window;
  }
  // App shells (e.g. Search Console) keep the window fixed and scroll one large inner element.
  function mainScroller() {
    const root = position(window);
    if (root.maxY > 0 || root.maxX > 0) return window;
    let best = window, area = 0;
    for (const el of allElements()) {
      if (el.clientHeight * el.clientWidth <= area || !scrollable(el) || !visible(el)) continue;
      best = el; area = el.clientHeight * el.clientWidth;
    }
    return best;
  }
  async function execute(op, args = {}) {
    if (!pageOps.has(op)) fail("UNSUPPORTED_OPERATION", "Unsupported page operation");
    if (args.expectedDocumentId !== undefined && args.expectedDocumentId !== epoch) fail("STALE_REFERENCE", "Document changed; observe the current page before acting");
    const responseFields = op === "read" || op === "locate" ? selectedResponseFields(args) : null;
    if (op === "webmcp_discover" || op === "webmcp_invoke") {
      if (typeof createWebMCPAdapter !== "function" || typeof normalizeWebMCPSettings !== "function") fail("WEBMCP_ADAPTER_MISSING", "Reload this tab to load the fixed WebMCP adapter");
      const stored = await browser.storage.local.get(["webmcp"]);
      const adapter = createWebMCPAdapter(document, window, {...normalizeWebMCPSettings(stored.webmcp), beforeInvoke: async toolName => {
        const latest = normalizeWebMCPSettings((await browser.storage.local.get(["webmcp"])).webmcp);
        if (!latest.enabled || !latest.allowedOrigins.includes(document.location.origin) || !latest.allowedToolNames.includes(toolName)) fail("WEBMCP_DISABLED", "WebMCP permission was removed before invocation");
      }});
      const capability = adapter.probe();
      if (op === "webmcp_discover" && !capability.supported) return {capability, tools: [], documentId: epoch, fallback: "DOM"};
      const result = op === "webmcp_discover" ? await adapter.discover() : await adapter.invoke({name: args.toolName, input: args.input, expectedSchema: args.expectedSchema, timeoutMs: args.timeoutMs});
      return {...result, documentId: epoch};
    }
    if (op === "click_point") { const start = viewportPoint(args.x, args.y), hit = hitAt(start); return hit ? observeEffect(hit, () => coordinateAction(op, args)) : coordinateAction(op, args); }
    if (op === "drag") return coordinateAction(op, args);
    if (op === "wait") {
      const timeout = Math.min(15000, Math.max(0, Number(args.timeoutMs ?? 5000))), state = args.state || "visible";
      if (!["visible", "hidden", "attached", "detached"].includes(state)) fail("INVALID_ARGUMENT", "Unknown wait state");
      return await new Promise((resolve, reject) => {
        let observer, timer, interval;
        function finish(error, result) { observer?.disconnect(); clearTimeout(timer); clearInterval(interval); error ? reject(error) : resolve(result); }
        function check() {
          try {
            const matches = find({...args, includeHidden: true}), shown = matches.filter(visible);
            const ready = state === "attached" ? matches.length > 0 : state === "detached" ? matches.length === 0 : state === "visible" ? shown.length > 0 : shown.length === 0;
            if (ready) finish(null, {state, count: matches.length, element: matches[0] ? describe(matches[0]) : null});
          } catch (error) { finish(error); }
        }
        observer = new MutationObserver(check); observer.observe(document, {subtree: true, childList: true, attributes: true});
        timer = setTimeout(() => finish(Object.assign(Error("Element wait timed out"), {code: "TIMEOUT"})), timeout);
        interval = setInterval(check, 100); check();
      });
    }
    if (op === "read") {
      const root = args.selector || args.ref || semanticArgs(args) ? one(args) : document.body;
      if (!root) return {url: location.href, title: document.title, readyState: document.readyState, text: "", elements: [], scroll: position(window), viewport: viewportInfo()};
      const limit = Math.min(100000, Math.max(0, Number(args.textLimit ?? 12000))), max = Math.min(500, Math.max(0, Number(args.maxElements ?? 120)));
      const offset = Math.max(0, Number(args.offset || 0)), textOffset = Math.max(0, Number(args.textOffset || 0)), cache = new WeakMap();
      const text = args.text === false ? "" : root.innerText || root.textContent || "";
      const selector = "a,button,input,textarea,select,[role=button],[role=textbox],[contenteditable=true],summary";
      const candidates = [], roots = [root];
      if (max > 0 && root.matches?.(selector)) candidates.push(root);
      for (let i = 0; max > 0 && i < roots.length; i++) {
        for (const el of roots[i].querySelectorAll(selector)) candidates.push(el);
        for (const el of roots[i].querySelectorAll("*")) if (el.shadowRoot) roots.push(el.shadowRoot);
      }
      const selected = args.includeHidden ? candidates : candidates.filter(visible);
      return {url: location.href, title: document.title, readyState: document.readyState,
        text: text.slice(textOffset, textOffset + limit), textLength: text.length, textTruncated: textOffset + limit < text.length,
        elements: selected.slice(offset, offset + max).map(el => describe(el, cache, args.selectors !== false, responseFields)),
        elementCount: max > 0 ? selected.length : null, ...(max === 0 ? {elementsComplete: false} : {}), nextOffset: offset + max < selected.length ? offset + max : null,
        scroll: position(window), viewport: viewportInfo(), documentId: epoch};
    }
    // CSS selectors also match hidden copies (app shells keep many); semantic queries already skip them.
    if (op === "locate") { const matches = semanticArgs(args) || args.ref || args.includeHidden ? find(args) : find(args).filter(el => visible(el)), cache = new WeakMap(); return {count: matches.length, elements: matches.slice(0, Math.min(500, Math.max(0, Number(args.maxElements ?? 100)))).map(el => describe(el, cache, args.selectors !== false, responseFields))}; }
    if (op === "scroll") {
      const mode = args.mode || "relative", behavior = args.behavior || "instant";
      if (!["relative", "absolute", "intoView"].includes(mode) || !["instant", "smooth", "auto"].includes(behavior)) fail("INVALID_ARGUMENT", "Unknown scroll mode or behavior");
      const element = args.selector || args.ref || semanticArgs(args) ? one(args) : null;
      if (mode === "intoView" && !element) fail("INVALID_ARGUMENT", "intoView requires selector or ref");
      // intoView reports the container that actually moved; a window scroll falls back to the main inner scroller.
      const target = mode === "intoView" ? scrollContainer(element) : element || mainScroller(), before = position(target);
      if (mode === "intoView") element.scrollIntoView({block: args.block || "center", inline: "nearest", behavior});
      else {
        const x = Number(args.x ?? (mode === "relative" ? 0 : before.x)), y = Number(args.y ?? (mode === "relative" ? 500 : before.y));
        if (!Number.isFinite(x) || !Number.isFinite(y)) fail("INVALID_ARGUMENT", "Scroll coordinates must be finite");
        if (mode === "relative") target.scrollBy({left: x, top: y, behavior});
        else target.scrollTo({left: x, top: y, behavior});
      }
      if (behavior === "smooth") await new Promise(resolve => {
        let last = position(target), quiet = 0;
        const started = performance.now();
        const timer = setInterval(() => {
          const current = position(target);
          quiet = current.x === last.x && current.y === last.y ? quiet + 1 : 0; last = current;
          if (quiet >= 3 || performance.now() - started > 2000) { clearInterval(timer); resolve(); }
        }, 50);
      });
      return {before, after: position(target), window: position(window), ...(target !== window ? {container: {ref: reference(target), tag: target.tagName.toLowerCase()}} : {})};
    }
    const el = one(args);
    if (op === "inspect") {
      const result = describe(el);
      result.focused = el === el.getRootNode().activeElement;
      result.readOnly = !!el.readOnly;
      if ("value" in el && el.type !== "password") result.value = String(el.value).slice(0, 4096);
      if (el instanceof HTMLSelectElement) result.options = [...el.options].map(option => ({value: option.value, text: option.text, selected: option.selected, disabled: option.disabled}));
      if (el.isContentEditable) result.value = el.textContent.slice(0, 4096);
      if (args.layout === true) result.layout = layoutInfo(el);
      return result;
    }
    actionable(el, args, ["fill", "type", "clear", "press"].includes(op));
    if (op === "click" || op === "double_click") return observeEffect(el, async () => {
      const point = await mouseClick(el, args, 1);
      if (op === "double_click") { await mouseClick(el, args, 2); el.dispatchEvent(new MouseEvent("dblclick", {...point, detail: 2})); }
      return {ok: true, ref: reference(el)};
    });
    if (op === "hover") {
      const point = await pointer(el, args);
      for (const name of ["mouseover", "mouseenter", "mousemove"]) el.dispatchEvent(new MouseEvent(name, {...point, bubbles: name !== "mouseenter"}));
      return {ok: true};
    }
    if (op === "focus") { el.focus({preventScroll: true}); return {focused: el === el.getRootNode().activeElement}; }
    if (["fill", "type", "clear"].includes(op)) {
      el.focus({preventScroll: true});
      const text = op === "clear" ? "" : String(args.value ?? "");
      if (op === "type") {
        for (const key of text) {
          if (el.dispatchEvent(new KeyboardEvent("keydown", {key, bubbles: true, cancelable: true}))) insertText(el, key);
          el.dispatchEvent(new KeyboardEvent("keyup", {key, bubbles: true}));
        }
      } else setText(el, text, op === "clear" ? "deleteContentBackward" : "insertText");
      el.dispatchEvent(new Event("change", {bubbles: true}));
      return {ok: true, length: editableText(el).length};
    }
    if (op === "select") {
      if (!(el instanceof HTMLSelectElement)) fail("INVALID_TARGET", "select requires a select element");
      const values = args.values || [String(args.value ?? "")];
      if (!Array.isArray(values) || !values.length || (!el.multiple && values.length !== 1)) fail("INVALID_ARGUMENT", "Invalid selected values");
      for (const value of values) if (![...el.options].some(option => option.value === value && !option.disabled && !option.parentElement.disabled)) fail("INVALID_VALUE", "Option missing or disabled");
      for (const option of el.options) option.selected = values.includes(option.value);
      el.dispatchEvent(new Event("input", {bubbles: true})); el.dispatchEvent(new Event("change", {bubbles: true}));
      return {values: [...el.selectedOptions].map(option => option.value)};
    }
    if (op === "check") {
      if (!(el instanceof HTMLInputElement) || !["checkbox", "radio"].includes(el.type)) fail("INVALID_TARGET", "check requires checkbox or radio");
      const checked = args.checked ?? true;
      if (typeof checked !== "boolean" || (el.type === "radio" && !checked)) fail("INVALID_ARGUMENT", "Radio buttons can only be checked; checked must be boolean");
      if (el.checked !== checked) el.click();
      return {checked: el.checked};
    }
    if (op === "press") return observeEffect(el, () => pressKey(el, args));
    fail("UNSUPPORTED_OPERATION", "Unsupported page operation");
  }
  function pressKey(el, args) {
    el.focus({preventScroll: true});
    const keys = String(args.key || "").split("+"), key = keys.pop();
    if (!key) fail("INVALID_ARGUMENT", "key required");
    const modifiers = {ctrlKey: keys.includes("Control"), metaKey: keys.includes("Meta"), shiftKey: keys.includes("Shift"), altKey: keys.includes("Alt")};
    const allowed = el.dispatchEvent(new KeyboardEvent("keydown", {key, ...modifiers, bubbles: true, cancelable: true}));
    if (allowed) {
      if ((modifiers.ctrlKey || modifiers.metaKey) && key.toLowerCase() === "a" && typeof el.select === "function") el.select();
      else if ((modifiers.ctrlKey || modifiers.metaKey) && key.toLowerCase() === "a" && el.isContentEditable) { const selection = window.getSelection(); selection.removeAllRanges(); const range = document.createRange(); range.selectNodeContents(el); selection.addRange(range); }
      else if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(key) && el.selectionStart !== null && typeof el.setSelectionRange === "function") {
        const start = el.selectionStart, end = el.selectionEnd, length = editableText(el).length;
        const target = key === "Home" ? 0 : key === "End" ? length : key === "ArrowLeft" ? Math.max(0, (modifiers.shiftKey ? end : start) - (start !== end && !modifiers.shiftKey ? 0 : 1)) : Math.min(length, end + (start !== end && !modifiers.shiftKey ? 0 : 1));
        el.setSelectionRange(modifiers.shiftKey ? Math.min(start, target) : target, modifiers.shiftKey ? Math.max(start, target) : target);
      }
      else if ((key === "Enter" || key === " " || key === "Space") && ["button", "checkbox", "radio", "link"].includes(roleOf(el))) el.click();
      else if (key === "Enter" && el instanceof HTMLInputElement && el.form) el.form.requestSubmit();
      else if (key === "Enter" && el instanceof HTMLTextAreaElement) insertText(el, "\n", "insertLineBreak");
      else if (["Backspace", "Delete"].includes(key)) {
        const value = editableText(el), start = el.selectionStart ?? value.length, end = el.selectionEnd ?? value.length;
        const from = start === end && key === "Backspace" ? Math.max(0, start - 1) : start;
        const to = start === end && key === "Delete" ? Math.min(value.length, end + 1) : end;
        setText(el, value.slice(0, from) + value.slice(to), key === "Backspace" ? "deleteContentBackward" : "deleteContentForward");
        if (typeof el.setSelectionRange === "function" && el.selectionStart !== null) el.setSelectionRange(from, from);
      } else if (key === "Tab") {
        const fields = [...document.querySelectorAll("a[href],button,input,textarea,select,[tabindex],[contenteditable=true]")].filter(element => visible(element) && enabled(element) && element.tabIndex >= 0);
        const next = fields[(fields.indexOf(el) + (modifiers.shiftKey ? -1 : 1) + fields.length) % fields.length]; next?.focus({preventScroll: true});
      } else if (key.length === 1 && !modifiers.ctrlKey && !modifiers.metaKey && !modifiers.altKey) insertText(el, key);
    }
    el.dispatchEvent(new KeyboardEvent("keyup", {key, ...modifiers, bubbles: true}));
    return {ok: true, defaultPrevented: !allowed};
  }
  const listener = message => {
    if (message?.type !== "browser-bridge.command" || globalThis.__browserBridgePageVersion !== engineVersion) return undefined;
    if (message.engineVersion && message.engineVersion !== engineVersion) return Promise.resolve({engineVersion, error: {code: "ENGINE_VERSION_MISMATCH", message: "Reload this tab to update the page interaction engine"}});
    return execute(message.op, message.args || {}).then(result => ({engineVersion, result})).catch(error => ({engineVersion, error: {code: error.code || "PAGE_ERROR", message: error.message, ...(typeof error.actionMayHaveOccurred === "boolean" ? {actionMayHaveOccurred: error.actionMayHaveOccurred} : {}), ...(error.nextSteps ? {nextSteps: error.nextSteps} : {})}}));
  };
  globalThis.__browserBridgePageListener = listener;
  browser.runtime.onMessage.addListener(listener);
})();
