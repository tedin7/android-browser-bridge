# 0.3.1 development — lean MCP responses and fixed desktop layout audits

Compact browser_command responses are now the default: read starts at 2,000
text characters and 20 controls, locate at 20 controls, preserving refs, counts,
truncation, document/viewport evidence and safety metadata. Explicit limits win;
full restores the previous output and fields selects top-level properties.
Duplicate labels and long attributes/frame URLs are reduced with explicit flags.
Screenshot results in batches become MCP images rather than base64 inside JSON.

Updated agent guidance favors targeted DOM operations, confirmed devices and tab
IDs, batches and proportionate verification. Screenshots remain available when
visual evidence is required. Raw logs/HTML/tables should stay in evidence files.
Text response optimization also works with older installed Android extensions.

Extension 0.3.1 adds optional fixed inspect layout metadata and a desktop-only
viewport command. desktop_audit.py uses Firefox plus our MCP in a temporary
profile, without Playwright or arbitrary page JavaScript, and no screenshots
unless requested. Measured viewport matching and explicit limits prevent
claiming Android rendering or requested sizes that were not actually observed.

See docs/TOKEN_EFFICIENCY.md, docs/DESKTOP_AUDIT.md and docs/VALIDATION.md for
usage and measured verification. The XPI remains unsigned; no AMO approval.
