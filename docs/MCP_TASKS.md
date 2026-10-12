# MCP Tasks polling adapter

`mcp_tasks.py` implements the polling subset of the official
`io.modelcontextprotocol/tasks` extension for modern MCP 2026-07-28 clients.
The adapter requires explicit per-request client capability opt-in; other
clients keep synchronous `browser_step` behavior.

An opted-in `browser_step` may return a durable task handle. `tasks/get` returns
its state and, on completion, the same serialized workflow receipt shape as the
synchronous tool. `tasks/cancel` acknowledges a cooperative request; it does not
undo browser effects or promise that the final state will be cancelled.
Interrupted/uncertain runtime outcomes map to failed tasks with an explicit
uncertainty receipt. The adapter creates no input requests; `tasks/update`
acknowledges and ignores unmatched response keys. There are no task notifications
or subscriptions in this subset.

Creation and polling use the flat 2026-07-28 shapes, not the legacy nested task
format. Timestamps are UTC ISO 8601; TTL is measured from creation, not each poll.
The server must advertise the extension only when authenticated callbacks are
wired and full result retention is enabled. Callbacks derive ownership from the
actual broker credential, never clientInfo metadata or caller-supplied client IDs.

`TaskRuntime.submit(..., retain_result=True)` explicitly retains a bounded full
step receipt as a private artifact before committing terminal completion.
`get(..., include_result=True)` retrieves it for the shared MCP serializer. This
retention can include output fields requested by the workflow. Plain runtime
tasks retain only constrained metadata by default; nothing is written to logs.

Sources verified on 2026-10-12:

- [Official Tasks overview](https://modelcontextprotocol.io/extensions/tasks/overview).
- [Released 2026-07-28 schema](https://github.com/modelcontextprotocol/ext-tasks/blob/main/schema/2026-07-28/schema.ts).

Unit tests cover the implemented subset and durable result recovery. They are
not certification of every optional MCP Tasks behavior or a claim that all
Codex/Claude versions support this extension.
