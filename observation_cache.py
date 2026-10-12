"""Bounded, private in-memory observations; no persistence or page execution.

Callers supply an authenticated client identity and the *complete* effective read
arguments as region_args (including projections/limits). A delta changes only
whole top-level fields. Lists are replaced, never patched by guessed identity.
"""
from collections import OrderedDict
import copy
import json
import threading
import time
import uuid


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


class ObservationCache:
    def __init__(self, max_snapshots=128, max_bytes=4 * 1024 * 1024,
                 ttl_seconds=120, clock=time.monotonic):
        if max_snapshots < 1 or max_bytes < 1 or ttl_seconds <= 0:
            raise ValueError("Observation cache limits must be positive")
        self.max_snapshots = max_snapshots
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    def _drop(self, snapshot):
        entry = self._entries.pop(snapshot)
        self._bytes -= entry["size"]

    def _expire(self, now):
        for snapshot, entry in list(self._entries.items()):
            if entry["expires"] <= now:
                self._drop(snapshot)

    def clear_client(self, client_id):
        """Forget observations on client revocation without exposing their data."""
        with self._lock:
            for snapshot, entry in list(self._entries.items()):
                if entry["scope"][0] == client_id:
                    self._drop(snapshot)

    def observe(self, *, client_id, device, tab_id, region_args,
                observation, since_snapshot=None):
        if not isinstance(client_id, str) or not client_id or not isinstance(device, str) or not device:
            raise ValueError("Authenticated client and device are required")
        if isinstance(tab_id, bool) or not isinstance(tab_id, int) or tab_id < 0:
            raise ValueError("An explicit tab ID is required")
        if not isinstance(region_args, dict) or not isinstance(observation, dict):
            raise ValueError("Region arguments and observation must be objects")
        if since_snapshot is not None and not isinstance(since_snapshot, str):
            raise ValueError("since_snapshot must be a snapshot identifier")
        region = _encoded(region_args)
        serialized = _encoded(observation)
        data = json.loads(serialized)
        document_id = data.get("documentId")
        response = {"mode": "full", "snapshotId": None,
                    "documentId": document_id, "data": data}
        if not isinstance(document_id, str) or not document_id:
            response["reason"] = "document_unavailable"
            return response
        scope = (client_id, device, tab_id)
        with self._lock:
            now = self._clock()
            self._expire(now)
            document_changed = False
            for snapshot, entry in list(self._entries.items()):
                if entry["scope"] == scope and entry["document"] != document_id:
                    document_changed = True
                    self._drop(snapshot)
            base = self._entries.get(since_snapshot)
            if base and (base["scope"] != scope or base["region"] != region):
                base = None
            size = len(serialized) + len(region) + len(_encoded(scope)) + 128
            if size > self.max_bytes:
                response["reason"] = "observation_too_large"
                return response
            snapshot_id = uuid.uuid4().hex
            if base is not None:
                changed = {key: value for key, value in data.items()
                           if key not in base["data"] or base["data"][key] != value}
                removed = sorted(set(base["data"]) - set(data))
                candidate = {"mode": "delta", "snapshotId": snapshot_id,
                             "baseSnapshotId": since_snapshot,
                             "documentId": document_id,
                             "changed": changed, "removed": removed}
                # A small full observation can cost less than delta metadata.
                if len(_encoded(candidate)) < len(_encoded(response)):
                    response = candidate
                else:
                    response["reason"] = "delta_not_smaller"
            elif since_snapshot is not None:
                response["reason"] = "document_changed" if document_changed else "snapshot_unavailable"
            response["snapshotId"] = snapshot_id
            # Input, retained state and returned data never alias each other.
            self._entries[snapshot_id] = {"scope": scope, "region": region,
                "document": document_id, "data": copy.deepcopy(data),
                "expires": now + self.ttl_seconds, "size": size}
            self._bytes += size
            while len(self._entries) > self.max_snapshots or self._bytes > self.max_bytes:
                self._drop(next(iter(self._entries)))
            return response

    def stats(self):
        """Counts only; never return identities or observation content."""
        with self._lock:
            self._expire(self._clock())
            return {"snapshots": len(self._entries), "bytes": self._bytes}
