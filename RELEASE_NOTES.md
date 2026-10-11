# 0.2.2 development — MCP update, extension unchanged at 0.2.1

Fixes Android history-navigation completion on the Linux MCP. Navigation is
submitted once with no browser-event wait; fixed read-only snapshots verify a
completed URL/document transition, including BFCache and same-URL reloads.
Compound commands maintain same-page FIFO and device barriers while independent
pages run concurrently. This update needs no Android extension reinstall when
0.2.1 is already installed.

The final actual Android full suite passed with MCP 0.2.2 and the unchanged
0.2.1 extension on OnePlus Pad 3. All 30 fixed operations passed, including
back/forward, multiple pages, semantic discovery, forms/keyboard, frames, open
shadow roots, canvas clicks/dragging, screenshots and batch failure boundaries.
Concurrent MCP requests verified that page B completes while page A waits.
The packaged MCP also passed the complete isolated Firefox Linux suite.

Twelve samples per operation in the final actual Android run measured median/p95
milliseconds: tabs 6.24/7.63, read 12.32/16.31, click 7.41/10.12, fill 8.42/15.41.
The earlier 0.1.2 baseline median was approximately 935–940 ms. These small local
fixture measurements are not guarantees for every website or network.

Thirty-four Python tests passed, including new navigation and compound-command
ordering regressions. Node scheduler/recovery tests passed. The unchanged
extension 0.2.1 had zero Mozilla lint errors, notices or warnings.

Version 0.2.1 features remain: optional explicitly bound Termux-local foreground
helper, structured agent errors and nextSteps, browser_status, rendered viewport
diagnostics, strict hit-testing and bounded page-response deadlines. Uncertain
actions are not automatically replayed. The local Android helper was exercised,
followed by a successful rendered-viewport suite.

Unsigned Nightly development package. Mozilla signing and marketplace review
remain pending. The same extension ID preserves existing pairing storage.
Android network endurance and 24/7 availability remain unverified. Installation
and extension upgrades require the documented user steps; foreground does not
operate Android's installer. No automatic-update bootstrap is active in the
installed extension. The MCP/source update can be performed from Linux.
