"""Broker-owned bounded workers for durable, leased browser workflows."""
from concurrent.futures import ThreadPoolExecutor
import secrets
import threading
import time
from action_store import needs_durable_identity
from step_runtime import execute_step, validate_plan, READ_ONLY


class TaskCancelled(Exception):
    pass


class TaskRuntime:
    def __init__(self, broker, store, workers=2, max_pending=8):
        if workers < 1 or max_pending < workers:
            raise ValueError("Invalid task worker limits")
        self.broker, self.store = broker, store
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="browser-task")
        self._slots = threading.BoundedSemaphore(max_pending)
        self._lock = threading.Lock()
        self._closed = False
        self._active = {}

    def submit(self, client_id, device, plan, *, allowed_devices=None, scoped_client=False, retain_result=False):
        if not isinstance(retain_result, bool):
            raise ValueError("retain_result must be boolean")
        validated = validate_plan(plan)
        # Explicit outputFields asks for a result; retaining it privately is
        # required even when the caller uses the plain browser_task API.
        retain_result = retain_result or bool(validated.get("outputFields"))
        if allowed_devices is not None and device not in allowed_devices:
            raise PermissionError("Device outside client scope")
        if scoped_client and allowed_devices is None:
            raise ValueError("Scoped clients require an authenticated device allowlist")
        with self._lock:
            if self._closed:
                raise RuntimeError("Task runtime is closed")
            if not self._slots.acquire(blocking=False):
                raise ValueError("TASK_QUEUE_FULL: all task slots are occupied")
            task = None
            try:
                task = self.store.create("browser_step", device, validated["tabId"], client_id)
                identifier = task["taskId"]
                self._active[identifier] = client_id
                self._executor.submit(self._run, identifier, client_id, device, validated, scoped_client, retain_result)
            except Exception:
                if task:
                    self._active.pop(task["taskId"], None)
                    self.store.finish(task["taskId"], "failed", {"code": "TASK_NOT_STARTED", "actionMayHaveOccurred": False}, client_id)
                self._slots.release()
                raise
        return task

    def get(self, task_id, client_id, include_result=False):
        if not isinstance(include_result, bool):
            raise ValueError("include_result must be boolean")
        result = self.store.get(task_id, client_id)
        if include_result and result["state"] != "working" and result.get("artifactId"):
            result["result"] = self.store.read_artifact(task_id, client_id)
        return result

    def cancel(self, task_id, client_id):
        return self.store.cancel(task_id, client_id)

    def _run(self, task_id, client_id, device, plan, scoped_client, retain_result=False):
        generation = None
        result = None
        workflow = "task_" + task_id
        deadline = time.monotonic() + plan.get("timeoutMs", 60000) / 1000
        action_may_have_occurred = False
        unknown = False
        last_identity = {}
        final_state, final_receipt = "failed", {"code": "TASK_FAILED", "actionMayHaveOccurred": False}

        def cancelled():
            return self.store.get(task_id, client_id)["cancelRequested"]

        def dispatch(op, args, timeout_ms, releasing=False):
            nonlocal action_may_have_occurred, unknown, last_identity
            if not releasing and cancelled():
                raise TaskCancelled()
            budget = min(timeout_ms / 1000, max(0, deadline - time.monotonic())) if not releasing else min(2, timeout_ms / 1000)
            if budget <= 0:
                raise TimeoutError("TASK_DEADLINE")
            values = dict(args)
            if generation is not None:
                values.update(workflowId=workflow, leaseGeneration=generation)
            action_id = values.pop('actionId', None)
            if action_id is None and needs_durable_identity(op, values):
                action_id = secrets.token_hex(16)
            data = {"device": device, "op": op, "args": values, "_client": client_id, "actionId": action_id}
            if scoped_client:
                data["_scopedClient"] = client_id
            accepted = self.broker.handle("/api/command", data)
            if op not in READ_ONLY and op not in {"acquire_lease", "release_lease"}:
                action_may_have_occurred = True
            if op not in {"acquire_lease", "release_lease"}:
                last_identity = {"commandId": accepted["id"]}
                if action_id is not None:
                    last_identity["actionId"] = action_id
            status = self.broker.wait_result(accepted["id"], budget, client_id)
            if status.get("state") != "done":
                if not releasing:
                    unknown = True
                raise TimeoutError("Command outcome unavailable")
            if status.get("error"):
                raise RuntimeError("Command failed")
            return status.get("result")

        try:
            if cancelled():
                raise TaskCancelled()
            budget = max(1, int((deadline - time.monotonic()) * 1000))
            lease = dispatch("acquire_lease", {"tabId": plan["tabId"], "workflowId": workflow,
                                              "ttlMs": min(60000, budget)}, budget)
            if not isinstance(lease, dict) or not isinstance(lease.get("leaseGeneration"), str):
                raise RuntimeError("Lease acquisition not confirmed")
            generation = lease["leaseGeneration"]
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            result = {**execute_step({**plan, "timeoutMs": remaining}, dispatch), "workflowId": workflow}
            if unknown:
                final_state = "unknown"
            elif cancelled() and result["state"] not in {"verified", "executed"}:
                final_state = "cancelled"
            elif result["state"] in {"verified", "executed"}:
                final_state = "completed"
            elif result["state"] == "unknown":
                final_state = "unknown"
            else:
                final_state = "failed"
            final_receipt = {"status": result["state"], "verified": bool(result.get("verified")),
                             "actionMayHaveOccurred": action_may_have_occurred, **last_identity}
            if result.get("code"):
                final_receipt["code"] = result["code"]
        except TaskCancelled:
            final_state = "cancelled"
            final_receipt = {"code": "CANCEL_REQUESTED", "actionMayHaveOccurred": action_may_have_occurred, **last_identity}
        except Exception:
            final_state = "unknown" if unknown or action_may_have_occurred else "failed"
            final_receipt = {"code": "TASK_INTERRUPTED", "actionMayHaveOccurred": action_may_have_occurred, **last_identity}
        finally:
            if generation is not None:
                try:
                    dispatch("release_lease", {"tabId": plan["tabId"]}, 2000, releasing=True)
                except Exception:
                    # The bounded extension lease expires independently. Never
                    # replay browser actions to compensate for release failure.
                    pass
            try:
                if retain_result and result is not None:
                    try:
                        self.store.save_artifact(task_id, result, client_id)
                    except Exception:
                        final_state = "unknown"
                        final_receipt.update(code="RESULT_RETENTION_FAILED", actionMayHaveOccurred=action_may_have_occurred)
                if final_state == "completed":
                    self.store.progress(task_id, 1, client_id)
                self.store.finish(task_id, final_state, final_receipt, client_id)
            finally:
                with self._lock:
                    self._active.pop(task_id, None)
                self._slots.release()

    def close(self, wait=True):
        with self._lock:
            self._closed = True
            active = list(self._active.items())
        for task_id, client_id in active:
            try:
                self.store.cancel(task_id, client_id)
            except KeyError:
                pass
        self._executor.shutdown(wait=wait)
