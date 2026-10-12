"""Dual-era MCP stdio adapter with optional resources and polling tasks.

Verified sources (2026-10-12):
https://modelcontextprotocol.io/specification/2026-07-28/server/discover
https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
https://modelcontextprotocol.io/specification/2026-07-28/schema

This is a bounded tools profile, not certification of full MCP conformance.
"""
import copy
import threading

MODERN_VERSION = "2026-07-28"
PREFIX = "io.modelcontextprotocol/"
LEGACY_VERSIONS = ("2024-11-05", "2025-03-26")


class ProtocolError(ValueError):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.data = data

    def as_error(self):
        result = {"code": self.code, "message": str(self)}
        if self.data is not None:
            result["data"] = self.data
        return result


class ProtocolAdapter:
    def __init__(self, handle_legacy, *, server_info, capabilities=None,
                 legacy_versions=LEGACY_VERSIONS, ttl_ms=60000, tasks_adapter=None):
        if not isinstance(server_info, dict) or any(not isinstance(server_info.get(key), str) or not server_info[key] for key in ("name", "version")):
            raise ValueError("Server name and version are required")
        # Optional tasks are advertised only when a concrete adapter is supplied.
        # Subscriptions are deliberately not advertised.
        if capabilities is not None and (set(capabilities)-{'tools','resources'} or any(value!={} for value in capabilities.values())):
            raise ValueError("This adapter supports tools/resources without subscriptions")
        if isinstance(ttl_ms, bool) or not isinstance(ttl_ms, int) or ttl_ms < 0:
            raise ValueError("ttl_ms must be a nonnegative integer")
        self.tasks_adapter = tasks_adapter
        self.handle_legacy = handle_legacy
        self.server_info = copy.deepcopy(server_info)
        self.capabilities = copy.deepcopy(capabilities) if capabilities is not None else {"tools": {}}
        if tasks_adapter is not None:
            self.capabilities['extensions']={'io.modelcontextprotocol/tasks':{}}
        self.legacy_versions = tuple(legacy_versions)
        self.supported_versions = [MODERN_VERSION, *self.legacy_versions]
        self.ttl_ms = ttl_ms
        self._legacy_initialized = False
        self._lock = threading.Lock()

    def _unsupported(self, requested):
        raise ProtocolError(-32022, "Unsupported protocol version",
                            {"supported": self.supported_versions[:], "requested": requested})

    def _complete(self, result, cacheable=False):
        if not isinstance(result, dict):
            raise ProtocolError(-32603, "Invalid internal MCP result")
        completed = copy.deepcopy(result)
        completed.setdefault("resultType", "complete")
        completed["_meta"] = {**completed.get("_meta", {}),
                              PREFIX + "serverInfo": copy.deepcopy(self.server_info)}
        if cacheable:
            completed.update(ttlMs=self.ttl_ms, cacheScope="private")
        return completed

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc", "2.0") != "2.0" or not isinstance(message.get("method"), str):
            raise ProtocolError(-32600, "Invalid request")
        if "id" not in message:
            # Notifications are one-way and cannot execute tools.
            return None
        identifier = message["id"]
        if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
            raise ProtocolError(-32600, "Request ID must be a string or integer")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise ProtocolError(-32602, "Params must be an object")
        meta = params.get("_meta", {})
        if not isinstance(meta, dict):
            raise ProtocolError(-32602, "Request metadata must be an object")
        method = message["method"]
        if method=='tools/call' and ('arguments' in params and not isinstance(params['arguments'],dict) or 'name' in params and not isinstance(params['name'],str)):
            raise ProtocolError(-32602,'Tool name must be a string and arguments an object')
        modern_metadata = any(key.startswith(PREFIX) for key in meta)
        if method == "initialize" and not modern_metadata:
            result = self.handle_legacy(message)
            with self._lock:
                self._legacy_initialized = True
            return result
        if not modern_metadata and method != "server/discover":
            with self._lock:
                legacy = self._legacy_initialized
            if legacy:
                return self.handle_legacy(message)
        version = meta.get(PREFIX + "protocolVersion")
        if not isinstance(version, str):
            raise ProtocolError(-32602, "Per-request protocol version is required")
        if version not in self.supported_versions:
            self._unsupported(version)
        client_caps = meta.get(PREFIX + "clientCapabilities")
        if not isinstance(client_caps, dict):
            raise ProtocolError(-32602, "Per-request client capabilities are required")
        client_info = meta.get(PREFIX + "clientInfo")
        if client_info is not None and (not isinstance(client_info, dict) or any(not isinstance(client_info.get(key), str) for key in ("name", "version"))):
            raise ProtocolError(-32602, "Client information requires name and version")
        if version != MODERN_VERSION:
            return self.handle_legacy(message)
        if method == "server/discover":
            return self._complete({"supportedVersions": self.supported_versions[:],
                                   "capabilities": copy.deepcopy(self.capabilities)}, cacheable=True)
        if self.tasks_adapter is not None:
            task_result=self.tasks_adapter.handle(message)
            if task_result is not None:return self._complete(task_result)
        methods={"tools/list","tools/call"}
        if "resources" in self.capabilities:methods.update({"resources/list","resources/read"})
        if method not in methods:
            raise ProtocolError(-32601, "Method is not supported by this adapter")
        result = self.handle_legacy(message)
        completed = self._complete(result, cacheable=method in {"tools/list","resources/list","resources/read"})
        if method == "tools/list":
            completed["tools"] = sorted(completed.get("tools", []), key=lambda tool: tool["name"])
        return completed
