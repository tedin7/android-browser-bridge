"""Polling subset of official MCP Tasks 2026-07-28 for browser_step.

Verified schema:
https://raw.githubusercontent.com/modelcontextprotocol/ext-tasks/main/schema/2026-07-28/schema.ts

Callbacks are already authenticated and client-scoped. ClientInfo metadata must
never select the owner. Completed results use the synchronous step serializer.
No input requests or subscriptions are advertised/generated.
"""
from datetime import datetime, timezone
import copy
import re
from protocol_adapter import MODERN_VERSION, PREFIX, ProtocolError
from step_runtime import validate_plan

EXTENSION = "io.modelcontextprotocol/tasks"


class MCPTasksAdapter:
    def __init__(self, start, get, cancel, serialize_result, poll_interval_ms=500):
        if isinstance(poll_interval_ms, bool) or not isinstance(poll_interval_ms, int) or poll_interval_ms < 1:
            raise ValueError("Invalid polling interval")
        self.start = start
        self.get = get
        self.cancel = cancel
        self.serialize_result = serialize_result
        self.poll_interval_ms = poll_interval_ms

    @staticmethod
    def opted_in(message):
        params = message.get("params", {})
        meta = params.get("_meta", {}) if isinstance(params, dict) else {}
        if not isinstance(meta, dict) or meta.get(PREFIX + "protocolVersion") != MODERN_VERSION:
            return False
        capabilities = meta.get(PREFIX + "clientCapabilities", {})
        extensions = capabilities.get("extensions", {}) if isinstance(capabilities, dict) else {}
        return isinstance(extensions, dict) and isinstance(extensions.get(EXTENSION), dict)

    @staticmethod
    def _date(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _task(self, value):
        state = value["state"]
        if state not in {"working", "completed", "failed", "cancelled", "unknown"}:
            raise ProtocolError(-32603, "Unsupported runtime task state")
        return {"taskId": value["taskId"], "status": "failed" if state == "unknown" else state,
                "createdAt": self._date(value["createdAt"]), "lastUpdatedAt": self._date(value["updatedAt"]),
                "ttlMs": max(0, round((value["expiresAt"] - value["createdAt"]) * 1000)),
                "pollIntervalMs": self.poll_interval_ms}

    def _lookup(self, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id):
            raise ProtocolError(-32602, "Invalid task identifier")
        try:
            return self.get({"taskId": task_id, "includeResult": True})
        except (KeyError, PermissionError):
            raise ProtocolError(-32602, "Task unavailable") from None

    def handle(self, message):
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise ProtocolError(-32602, "Params must be an object")
        step_call = method == "tools/call" and params.get("name") == "browser_step"
        task_method = method in {"tasks/get", "tasks/cancel", "tasks/update"}
        if not step_call and not task_method:
            return None
        if not self.opted_in(message):
            if step_call:
                return None  # Original synchronous callback remains available.
            raise ProtocolError(-32021, "Tasks capability is required", {"requiredCapabilities": {"extensions": {EXTENSION: {}}}})
        if step_call:
            args = params.get("arguments", {})
            if not isinstance(args, dict) or set(args) - {"device", "plan"} or not isinstance(args.get("device"), str) or not args["device"]:
                raise ProtocolError(-32602, "Expected browser_step device and plan")
            try:
                plan = validate_plan(args.get("plan"))
            except ValueError:
                raise ProtocolError(-32602, "Invalid browser_step plan") from None
            record = self.start({"device": args["device"], "plan": plan, "retainResult": True})
            return {"resultType": "task", **self._task(record)}
        record = self._lookup(params.get("taskId"))
        if method == "tasks/cancel":
            self.cancel({"taskId": params["taskId"]})
            return {"resultType": "complete"}
        if method == "tasks/update":
            if not isinstance(params.get("inputResponses"), dict):
                raise ProtocolError(-32602, "inputResponses must be an object")
            # This subset creates no input requests. All supplied keys are
            # unknown/already satisfied and must be ignored per specification.
            return {"resultType": "complete"}
        result = {"resultType": "complete", **self._task(record)}
        if record["state"] == "completed":
            if "result" not in record:
                raise ProtocolError(-32603, "Completed task result is unavailable")
            complete = self.serialize_result(copy.deepcopy(record["result"]))
            if not isinstance(complete, dict):
                raise ProtocolError(-32603, "Invalid serialized task result")
            result["result"] = {**complete, "resultType": "complete"}
        elif record["state"] in {"failed", "unknown"}:
            # Application-specific errors live outside the JSON-RPC reserved
            # range. Preserve uncertainty, never translate unknown to success.
            result["error"] = {"code": 1001, "message": "Browser workflow outcome is uncertain" if record["state"] == "unknown" else "Browser workflow failed",
                               "data": {"receipt": copy.deepcopy(record.get("receipt", {})), "outcomeUnknown": record["state"] == "unknown"}}
        return result
