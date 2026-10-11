# 0.2.1 development

Adds foreground control with an optional fixed Termux-local Android launcher,
structured agent errors and nextSteps, browser_status for uncertain command
outcomes, rendered viewport diagnostics, strict click hit-testing, and bounded
page response deadlines so a suspended Android tab cannot block the scheduler
indefinitely. No replay of actions with uncertain outcomes.

Firefox Linux integration and mocked recovery tests pass. Actual Android 0.2.0
testing exposed invisible viewport and suspended-tab behavior; those fixes require
installing this 0.2.1 extension before final Android validation and profiling.

Unsigned Nightly development package. Mozilla signing remains pending.
Same extension ID preserves existing pairing storage.
