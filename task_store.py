"""Durable local runtime tasks, independent of the optional MCP Tasks extension.

Only operation metadata and constrained receipts enter SQLite. Page results are
written solely by an explicit save_artifact call. Cancellation requests never
claim to undo effects; the worker must acknowledge its final state.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import threading
import time

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_TERMINAL = {"completed", "failed", "cancelled", "unknown"}
_RECEIPT = {"actionId", "commandId", "status", "verified", "actionMayHaveOccurred", "code"}


class TaskStore:
    def __init__(self, path, max_tasks=256, ttl_seconds=86400,
                 max_artifact_bytes=4 * 1024 * 1024, clock=time.time,
                 max_history=256, max_artifact_total_bytes=32 * 1024 * 1024):
        if max_tasks < 1 or ttl_seconds <= 0 or max_artifact_bytes < 1 or max_history < 1 or max_artifact_total_bytes < 1:
            raise ValueError("Task limits must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.artifacts = self.path.parent / (self.path.name + ".artifacts")
        self.artifacts.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.artifacts, 0o700)
        self.max_history = max_history
        self.max_artifact_total_bytes = max_artifact_total_bytes
        self.max_tasks, self.ttl_seconds = max_tasks, ttl_seconds
        self.max_artifact_bytes, self.clock = max_artifact_bytes, clock
        self._lock = threading.RLock()
        self._owner_fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self._owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._owner_fd)
            raise RuntimeError("Task store is already owned by another runtime") from None
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, client TEXT NOT NULL, operation TEXT NOT NULL,
          device TEXT NOT NULL, tab INTEGER, state TEXT NOT NULL,
          progress REAL NOT NULL, cancel_requested INTEGER NOT NULL,
          created REAL NOT NULL, updated REAL NOT NULL, expires REAL NOT NULL,
          receipt TEXT NOT NULL, artifact TEXT)""")
        # Exclusive runtime ownership proves previous workers cannot still own
        # this store. Do not resume or replay an interrupted browser action.
        self._db.execute("UPDATE tasks SET state='unknown',updated=?,receipt=? WHERE state='working'",
                         (self.clock(), json.dumps({"actionMayHaveOccurred": True, "code": "RUNTIME_RESTARTED"})))
        self._db.commit()
        retained = {row[0] for row in self._db.execute("SELECT artifact FROM tasks WHERE artifact IS NOT NULL")}
        for path in self.artifacts.iterdir():
            if path.name not in retained and (re.fullmatch(r"[a-f0-9]{32}\.json", path.name) or path.name.startswith(".pending-")):
                path.unlink(missing_ok=True)

    @staticmethod
    def _identifier(value):
        if not isinstance(value, str) or not _ID.fullmatch(value):
            raise ValueError("Invalid task metadata identifier")
        return value

    def _delete_rows(self, rows):
        for row in rows:
            if row["artifact"]:
                (self.artifacts / row["artifact"]).unlink(missing_ok=True)
            self._db.execute("DELETE FROM tasks WHERE id=?", (row["id"],))

    def _cleanup(self, protect=None):
        expired = self._db.execute("SELECT id,artifact FROM tasks WHERE expires<=?", (self.clock(),)).fetchall()
        self._delete_rows(expired)
        history = self._db.execute("SELECT id,artifact FROM tasks WHERE state!='working' ORDER BY updated,rowid").fetchall()
        excess = max(0, len(history) - self.max_history)
        self._delete_rows([row for row in history if row["id"] != protect][:excess])
        self._db.commit()

    def _reserve_artifact_bytes(self, incoming, protect):
        if incoming > self.max_artifact_total_bytes:
            raise ValueError("Artifact exceeds total retention budget")
        rows = self._db.execute("SELECT id,artifact,state FROM tasks WHERE artifact IS NOT NULL ORDER BY updated,rowid").fetchall()
        sizes = {row["id"]: (self.artifacts / row["artifact"]).stat().st_size for row in rows}
        total = sum(sizes.values())
        victims = []
        for row in rows:
            if total + incoming <= self.max_artifact_total_bytes:
                break
            if row["state"] != "working" and row["id"] != protect:
                victims.append(row)
                total -= sizes[row["id"]]
        if total + incoming > self.max_artifact_total_bytes:
            raise ValueError("Active artifacts occupy the retention budget")
        self._delete_rows(victims)
        self._db.commit()

    def _row(self, task_id, client_id):
        self._identifier(task_id)
        self._identifier(client_id)
        self._cleanup(protect=task_id)
        row = self._db.execute("SELECT * FROM tasks WHERE id=? AND client=?", (task_id, client_id)).fetchone()
        if row is None:
            raise KeyError("Task unavailable")
        return row

    @staticmethod
    def _view(row):
        result = {"taskId": row["id"], "operation": row["operation"], "device": row["device"],
                  "tabId": row["tab"], "state": row["state"], "progress": row["progress"],
                  "cancelRequested": bool(row["cancel_requested"]), "createdAt": row["created"],
                  "updatedAt": row["updated"], "expiresAt": row["expires"],
                  "receipt": json.loads(row["receipt"]), "resultAvailable": bool(row["artifact"]) and row["state"] != "working"}
        if row["artifact"]:
            result["artifactId"] = row["artifact"]
        return result

    def create(self, operation, device, tab_id=None, client_id="local"):
        for value in (operation, device, client_id):
            self._identifier(value)
        if tab_id is not None and (isinstance(tab_id, bool) or not isinstance(tab_id, int) or tab_id < 0):
            raise ValueError("Invalid tab ID")
        with self._lock:
            self._cleanup()
            if self._db.execute("SELECT count(*) FROM tasks WHERE state='working'").fetchone()[0] >= self.max_tasks:
                raise ValueError("Active task capacity reached; wait for a task to finish")
            task_id, now = secrets.token_hex(16), self.clock()
            self._db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,'working',0,0,?,?,?,'{}',NULL)",
                             (task_id, client_id, operation, device, tab_id, now, now, now + self.ttl_seconds))
            self._db.commit()  # Identifier is not exposed before durable commit.
            return self._view(self._row(task_id, client_id))

    def get(self, task_id, client_id="local"):
        with self._lock:
            return self._view(self._row(task_id, client_id))

    def progress(self, task_id, fraction, client_id="local"):
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 <= fraction <= 1:
            raise ValueError("Progress must be a fraction from zero to one")
        with self._lock:
            row = self._row(task_id, client_id)
            if row["state"] != "working" or fraction < row["progress"]:
                raise ValueError("Progress cannot move backward or update a terminal task")
            self._db.execute("UPDATE tasks SET progress=?,updated=? WHERE id=?", (fraction, self.clock(), task_id))
            self._db.commit()
            return self.get(task_id, client_id)

    def cancel(self, task_id, client_id="local"):
        with self._lock:
            row = self._row(task_id, client_id)
            if row["state"] == "working":
                self._db.execute("UPDATE tasks SET cancel_requested=1,updated=? WHERE id=?", (self.clock(), task_id))
                self._db.commit()
            return self.get(task_id, client_id)

    def finish(self, task_id, state, receipt=None, client_id="local"):
        receipt = {} if receipt is None else receipt
        if state not in _TERMINAL or not isinstance(receipt, dict):
            raise ValueError("Invalid terminal state or receipt")
        if set(receipt) - _RECEIPT:
            raise ValueError("Only constrained receipt metadata may be persisted")
        for key, value in receipt.items():
            if key in ("verified", "actionMayHaveOccurred"):
                if not isinstance(value, bool):
                    raise ValueError("Receipt outcome flags must be booleans")
            else:
                self._identifier(value)
        with self._lock:
            row = self._row(task_id, client_id)
            if row["state"] != "working":
                raise ValueError("Terminal task cannot be rewritten")
            self._db.execute("UPDATE tasks SET state=?,receipt=?,updated=? WHERE id=?",
                             (state, json.dumps(receipt, separators=(",", ":")), self.clock(), task_id))
            self._db.commit()
            return self.get(task_id, client_id)

    def save_artifact(self, task_id, data, client_id="local"):
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > self.max_artifact_bytes:
            raise ValueError("Artifact exceeds size limit")
        with self._lock:
            row = self._row(task_id, client_id)
            if row["artifact"]:
                raise ValueError("Task artifact is immutable")
            self._reserve_artifact_bytes(len(encoded), task_id)
            artifact = secrets.token_hex(16) + ".json"
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=self.artifacts)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.artifacts / artifact)
                directory = os.open(self.artifacts, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                self._db.execute("UPDATE tasks SET artifact=? WHERE id=?", (artifact, task_id))
                self._db.commit()
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {"artifactId": artifact, "bytes": len(encoded)}

    def read_artifact(self, task_id, client_id="local"):
        with self._lock:
            row = self._row(task_id, client_id)
            if not row["artifact"]:
                raise KeyError("Task has no artifact")
            with open(self.artifacts / row["artifact"], "rb") as stream:
                encoded = stream.read(self.max_artifact_bytes + 1)
            if len(encoded) > self.max_artifact_bytes:
                raise ValueError("Artifact exceeds size limit")
            return json.loads(encoded)

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
                fcntl.flock(self._owner_fd, fcntl.LOCK_UN)
                os.close(self._owner_fd)
