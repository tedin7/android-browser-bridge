# Timed page input (1.0.4)

Fixed operations only; no page scripts or game state access. These synthetic events remain untrusted. They cannot grant fullscreen activation, bypass Android overlays, or create a semantic entity list for canvas games.

`press` accepts `code` (e.g. KeyW, Space, ShiftRight), `location` (0–3), `inputMode` (`auto` or `page`) and `durationMs` (0–5000). Common letter, digit, function and navigation codes are inferred when omitted; explicit code overrides support physical-key layouts. Space is normalized to a literal space with code Space. Modifier key events include location and correct modifier state on release.

```json
{"device":"confirmed-firefox","op":"press","args":{"tabId":7,"selector":"canvas","key":"w","code":"KeyW","inputMode":"page","durationMs":1000}}
```

`page` dispatches keydown and keyup without emulating text insertion, Tab traversal or button activation. `auto` preserves form editing, while printable keys on a non-editable canvas no longer attempt text insertion or throw NOT_EDITABLE after keydown. Press is one down/up pair, not automatic key repeat. `type` also includes inferred physical codes.

`drag` accepts `durationMs` (0–5000). Moves are paced across the requested duration; zero remains immediate. Equal start/end coordinates allow a bounded stationary hold. Movement events retain buttons=1; release uses buttons=0.

```json
{"device":"confirmed-firefox","op":"drag","args":{"tabId":7,"x":100,"y":150,"toX":160,"toY":150,"dragSteps":20,"durationMs":1200}}
```

Input lifetimes listen for document hiding/pagehide and dispatch release in finally, including error paths. INPUT_CANCELED means an action may have partially happened: observe before retrying. Browser/OS process termination can destroy the engine; no script can guarantee release execution after process death. Browser scheduling also means requested milliseconds are pacing targets, not a real-time guarantee. Keep holds short, on explicit foreground tabs. Navigation, held-key steering and simultaneous multi-key input are not an autonomous game loop.

HTML elements retain .click() defaults. SVG elements without .click() receive one coordinate-bearing MouseEvent click after pointer/mouse down/up. no_visible_change now means lack of DOM evidence, not proof that a canvas ignored input; verify application state.

## Validation

`node test_game_input.js` checks physical code/location, timed key and pointer holds, release after visibility/pagehide cancellation, rejection of oversized duration before keydown and SVG fallback. The real Firefox integration suite includes a focusable canvas fixture that records actual key code, location and elapsed hold time, timed drag and SVG activation. Existing form editing and checkbox defaults remain covered by that suite. Desktop results do not establish Android installation/runtime; record deployment evidence separately.
