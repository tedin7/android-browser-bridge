# 0.2.0 development

Adds concurrent commands on different tabs, ordered actions on the same tab,
semantic locators, stable document references, iframe and open-shadow support,
viewport screenshots, coordinate clicks and dragging, richer forms and keyboard
operations, nested scrolling, waiting and bounded batches.

Replaces periodic one-second browser polling and status polling with event-driven
long polling and immediate result reporting. Keeps a resident page engine and
reuses HTTP connections. Performance is measured through browser_metrics and
the fixture-only Android profiler; final Android results require upgrading the
extension. No claim of measured Android speedup before that verification.

Unsigned development package. Mozilla signing and public marketplace listing
remain pending. Existing pairing storage is preserved by the same extension ID.
