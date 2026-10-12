package net.arvos.browserbridge.companion

import android.accessibilityservice.AccessibilityService
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class BridgeAccessibilityService : AccessibilityService() {
    private val alive = AtomicBoolean(false)
    private val main = Handler(Looper.getMainLooper())
    private lateinit var state: ConnectionState
    private val session = java.util.UUID.randomUUID().toString()
    private var epoch = 0L
    private var refCounter = 0L
    private val references = mutableMapOf<String, Pair<AccessibilityNodeInfo, String>>()
    private var worker: Thread? = null

    override fun onServiceConnected() {
        state = ConnectionState(this)
        // Android enabling the service is separate from the app's remote-control consent.
        if (alive.compareAndSet(false, true)) worker = Thread({ runConnection() }, "bridge-native-serial").apply { start() }
    }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) { epoch++; references.clear() }
    }
    override fun onInterrupt() { if (::state.isInitialized) { state.enabled = false; state.status = "Interrupted: control stopped" } }
    override fun onDestroy() {
        alive.set(false); worker?.interrupt()
        if (::state.isInitialized) { state.enabled = false; state.status = "Accessibility service stopped" }
        getSystemService(NotificationManager::class.java).cancel(1)
        super.onDestroy()
    }
    private fun pause(milliseconds: Long) { try { Thread.sleep(milliseconds) } catch (_: InterruptedException) { } }
    private fun runConnection() {
        var backoff = 1000L
        while (alive.get()) {
            if (!state.enabled && state.pending == null) { getSystemService(NotificationManager::class.java).cancel(1); pause(500); continue }
            try {
                val snapshot = synchronized(ConnectionState.connectionLock) { Pair(state.connection(), state.pending) }
                val connection = snapshot.first
                if (connection == null) { state.enabled = false; state.status = "Pair a server first"; pause(500); continue }
                if (state.enabled) showStopNotification()
                val origin = connection.getString("url"); val token = connection.getString("token"); val device = connection.getString("device")
                val pending = snapshot.second
                if (pending != null) {
                    try {
                        BrokerTransport.request(origin, "/api/result", pending, token)
                        synchronized(ConnectionState.connectionLock) {
                            if (state.connection()?.optString("connectionId") == connection.optString("connectionId")) {
                                state.pending = null; state.status = "Connected: result delivered"
                            }
                        }
                    } catch (error: HttpFailure) {
                        if (error.status in 400..499 && error.status != 429) {
                            synchronized(ConnectionState.connectionLock) {
                                if (state.connection()?.optString("connectionId") == connection.optString("connectionId")) {
                                    state.pending = null
                                    state.status = "Result delivery rejected (${error.code}); action will not repeat"
                                    if (error.status == 401 || error.status == 403) state.enabled = false
                                }
                            }
                        } else throw error
                    }
                    continue
                }
                if (!state.enabled) continue
                val response = BrokerTransport.request(origin, "/api/poll", JSONObject().put("device", device).put("version", "companion-0.1.2").put("waitMs", 15000), token)
                backoff = 1000; state.status = "Connected: waiting for an authorized command"
                val command = response.optJSONObject("command") ?: continue
                val id = command.getString("id")
                val needsApproval = command.optString("op") in setOf("click", "fill", "scroll", "back")
                val approved = !needsApproval || awaitApproval(command, connection)
                val task = FutureTask<JSONObject> {
                    synchronized(ConnectionState.connectionLock) {
                        if (!approved) denied("APPROVAL_REQUIRED", "The action was denied, stopped or not approved before expiry. It was not performed")
                        else if (state.connection()?.optString("connectionId") != connection.optString("connectionId")) denied("CONNECTION_CHANGED", "This command belongs to a replaced connection; do not replay it")
                        else if (needsApproval && rootInActiveWindow?.packageName?.toString() != command.optString("_approvedPackage")) denied("CONTEXT_CHANGED", "Return to the originally approved app and inspect it before sending another action")
                        else execute(command.optString("op"), command.optJSONObject("args") ?: JSONObject())
                    }
                }
                main.post(task)
                val payload = JSONObject().put("device", device).put("id", id)
                try { payload.put("result", task.get(5, TimeUnit.SECONDS)) }
                catch (_: Exception) {
                    task.cancel(false)
                    payload.put("error", "NATIVE_ACTION_UNCERTAIN: inspect the device before repeating; native operation did not provide a confirmed result")
                }
                // Persist delivery only, never a command to replay after a restart.
                synchronized(ConnectionState.connectionLock) {
                    if (state.connection()?.optString("connectionId") == connection.optString("connectionId")) state.pending = payload
                }
            } catch (error: HttpFailure) {
                if (error.status == 401 || error.status == 403) { state.enabled = false; state.status = "Connection revoked: pair again" }
                else { state.status = "Broker unavailable (${error.status}); reconnecting"; pause(backoff); backoff = (backoff * 2).coerceAtMost(30000) }
            } catch (_: Exception) {
                state.status = "Connection unavailable; check broker address and network"
                pause(backoff); backoff = (backoff * 2).coerceAtMost(30000)
            }
        }
    }
    private fun awaitApproval(command: JSONObject, connection: JSONObject): Boolean {
        val contextTask = FutureTask<String> { rootInActiveWindow?.packageName?.toString() ?: "" }
        main.post(contextTask)
        val target = try { contextTask.get(3, TimeUnit.SECONDS) } catch (_: Exception) { contextTask.cancel(false); return false }
        if (!Policy.authorized(state.enabled, state.allowed, target, packageName)) return false
        val approval = JSONObject().put("id", command.getString("id")).put("operation", command.optString("op"))
            .put("package", target).put("args", command.optJSONObject("args") ?: JSONObject())
            .put("expiresAt", System.currentTimeMillis() + 30000).put("decision", "pending")
        command.put("_approvedPackage", target)
        state.approval = approval
        state.status = "Waiting for your approval: ${command.optString("op")} in $target"
        showStopNotification(approval)
        try {
            while (alive.get() && state.enabled && System.currentTimeMillis() < approval.getLong("expiresAt")) {
                if (state.connection()?.optString("connectionId") != connection.optString("connectionId")) return false
                when (state.approval?.optString("decision")) {
                    "approved" -> return true
                    "denied", null -> return false
                }
                pause(100)
            }
            return false
        } finally { state.approval = null; showStopNotification() }
    }
    private fun showStopNotification(approval: JSONObject? = null) {
        val manager = getSystemService(NotificationManager::class.java)
        if (!state.enabled) { manager.cancel(1); return }
        if (!manager.areNotificationsEnabled()) { state.enabled = false; state.status = "Allow notifications to keep a visible STOP control"; return }
        manager.createNotificationChannel(NotificationChannel("control", "Remote control", NotificationManager.IMPORTANCE_LOW))
        val stop = PendingIntent.getBroadcast(this, 1, Intent(this, StopReceiver::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 2, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        try {
            val notification = Notification.Builder(this, "control").setSmallIcon(android.R.drawable.ic_menu_view)
                .setContentTitle(if (approval == null) "Browser Bridge native control enabled" else "Approve ${approval.optString("operation")} in ${approval.optString("package")}")
                .setContentText(if (approval == null) "Only your allowed apps. Tap STOP to disconnect." else "Open details or approve once. Expires in 30 seconds.")
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .setContentIntent(open).setOngoing(true).addAction(Notification.Action.Builder(null, "STOP", stop).build())
            if (approval != null) {
                notification.setStyle(Notification.BigTextStyle().bigText("Requested arguments: " + (approval.optJSONObject("args") ?: JSONObject()).toString().take(12000)))
                for ((request, allowed) in listOf(3 to true, 4 to false)) {
                    val decision = PendingIntent.getBroadcast(this, request, Intent(this, ApprovalReceiver::class.java)
                        .putExtra("id", approval.getString("id")).putExtra("approve", allowed), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                    notification.addAction(Notification.Action.Builder(null, if (allowed) "Approve once" else "Deny", decision).build())
                }
            }
            manager.notify(1, notification.build())
        } catch (_: SecurityException) { state.enabled = false; state.status = "Allow notifications to keep a visible STOP control" }
    }
    private fun fingerprint(node: AccessibilityNodeInfo): String = listOf(node.windowId, node.packageName, node.viewIdResourceName, node.className, node.text, node.contentDescription).joinToString("|")
    private fun role(node: AccessibilityNodeInfo): String = when {
        node.isEditable -> "textbox"
        node.isCheckable -> "checkbox"
        node.isClickable -> "button"
        else -> "element"
    }
    private fun label(node: AccessibilityNodeInfo): String = Policy.accessibleLabel(node.contentDescription, node.text, node.hintText)
    private fun descriptor(node: AccessibilityNodeInfo): JSONObject {
        val ref = "native-$session-$epoch-${++refCounter}"
        if (references.size >= 1000) references.clear()
        references[ref] = Pair(AccessibilityNodeInfo.obtain(node), fingerprint(node))
        return JSONObject().put("ref", ref).put("role", role(node)).put("accessibleName", label(node)).put("visible", node.isVisibleToUser).put("enabled", node.isEnabled)
            .put("value", if (node.isPassword || !node.isEditable) JSONObject.NULL else node.text?.toString()?.take(2000) ?: "")
    }
    private fun execute(operation: String, args: JSONObject): JSONObject {
        if (!state.enabled) return denied("CONTROL_DISABLED", "Enable remote control in the companion first")
        if (operation !in Policy.operations) return denied("UNSUPPORTED_OPERATION", "Use the companion capabilities operation; browser and native capabilities differ")
        val activeRoot = rootInActiveWindow // execute runs on the main thread; never select a background window.
        val foreground = activeRoot?.packageName?.toString() ?: ""
        val allowedPackages = JSONArray(state.allowed.sorted())
        if (operation == "capabilities") return JSONObject().put("version", "0.1.2-experimental").put("backend", "android-accessibility")
            .put("foregroundPackage", foreground).put("allowedPackages", allowedPackages)
            .put("operations", JSONArray(Policy.operations.sorted())).put("nativeAndroidUI", true).put("browserTabs", false).put("screenshots", false).put("trustedEvents", false).put("targetedRead", false).put("allowlistedPackages", true).put("approvalRequiredForWrites", true).put("workflowLeases", false)
            .put("limits", JSONObject().put("maxNodes",1000).put("maxElements",50).put("textLimit",4000).put("shareBytes",1048576))
        val root = activeRoot ?: return denied("NO_ACTIVE_WINDOW", "Unlock the tablet and open an allowed app yourself")
        if (!Policy.authorized(state.enabled, state.allowed, foreground, packageName)) return denied("PACKAGE_NOT_ALLOWED", "The active Android window belongs to foregroundPackage. Dismiss system overlays or open an already allowed app; compare allowedPackages. Do not add packages automatically.").apply {
            getJSONObject("error").put("foregroundPackage", foreground).put("allowedPackages", allowedPackages)
        }
        if (args.has("selector") || args.has("frameId") || args.has("tabId")) return denied("UNSUPPORTED_TARGET", "Native controls use ref/name/role/label/textQuery, not CSS selectors, frames or browser tab IDs")
        if (operation == "back") return JSONObject().put("executed", performGlobalAction(GLOBAL_ACTION_BACK)).put("verified", false).put("nextSteps", JSONArray().put("Read the active app to verify the resulting screen"))
        val queue = ArrayDeque<AccessibilityNodeInfo>(); queue.add(root)
        val nodes = mutableListOf<AccessibilityNodeInfo>()
        while (queue.isNotEmpty() && nodes.size < 1000) {
            val node = queue.removeFirst(); nodes.add(node)
            for (i in 0 until node.childCount) node.getChild(i)?.let { queue.add(it) }
        }
        val complete = queue.isEmpty()
        if (operation == "read") {
            if (listOf("ref", "name", "label", "role", "textQuery").any { args.has(it) }) return denied("UNSUPPORTED_TARGET", "Use locate then inspect for a targeted native observation")
            val limit = Policy.bounded(args.optInt("textLimit", 2000), 0, 4000)
            val observedText = StringBuilder()
            var textTruncated = false
            for (node in nodes) {
                if (node.isPassword || !node.isVisibleToUser) continue
                val value = node.text ?: continue
                if (observedText.isNotEmpty()) observedText.append('\n')
                val remaining = (limit + 1 - observedText.length).coerceAtLeast(0)
                observedText.append(value.subSequence(0, minOf(value.length, remaining)))
                if (observedText.length > limit || value.length > remaining) { textTruncated = true; break }
            }
            val text = observedText.toString()
            val controls = nodes.filter { it.isVisibleToUser && !it.isPassword && (it.isClickable || it.isEditable || it.isScrollable) }
            val max = Policy.bounded(args.optInt("maxElements", 20), 0, 50)
            return JSONObject().put("backend", "android-accessibility").put("package", foreground).put("documentId", "native-$session-$epoch")
                .put("complete", complete).put("text", text.take(limit)).put("textLength", text.length).put("textLengthExact", !textTruncated && complete).put("textTruncated", textTruncated || !complete)
                .put("elementCount", controls.size).put("truncated", controls.size > max || !complete)
                .put("elements", JSONArray(controls.take(max).map { descriptor(it) }))
        }
        val ref = args.optString("ref")
        val matches = if (ref.isNotEmpty()) {
            val recorded = references[ref] ?: return denied("STALE_REFERENCE", "Locate the control again before acting")
            if (!recorded.first.refresh() || fingerprint(recorded.first) != recorded.second || recorded.first.packageName?.toString() != foreground || recorded.first.windowId != root.windowId) return denied("STALE_REFERENCE", "The control changed; locate and inspect it again")
            listOf(recorded.first)
        } else nodes.filter { node ->
            val exact = args.optBoolean("exact", true)
            fun match(key: String, actual: String): Boolean = !args.has(key) || if (exact) actual == args.getString(key) else actual.contains(args.getString(key), ignoreCase = true)
            node.packageName?.toString() == foreground && node.isVisibleToUser && !node.isPassword && match("name", label(node)) && match("label", label(node)) && match("textQuery", node.text?.toString() ?: "") && match("role", role(node))
        }
        if (operation == "locate") return JSONObject().put("elements", JSONArray(matches.filter { !it.isPassword }.take(Policy.bounded(args.optInt("maxElements",20),0,50)).map { descriptor(it) })).put("count", matches.size).put("complete", complete)
        if (!complete && ref.isEmpty()) return denied("OBSERVATION_INCOMPLETE", "Use a confirmed ref from a targeted observation")
        if (matches.size != 1) return denied("TARGET_NOT_UNIQUE", "Locate one exact control and use its ref")
        val node = matches.single()
        if (node.packageName?.toString() != foreground || node.windowId != root.windowId || node.isPassword || !node.isVisibleToUser || !node.isEnabled) return denied("TARGET_UNAVAILABLE", "Choose a visible enabled non-password control")
        if (operation == "inspect") return descriptor(node)
        // Recheck consent and foreground immediately before a write.
        if (!Policy.authorized(state.enabled, state.allowed, rootInActiveWindow?.packageName?.toString() ?: "", packageName)) return denied("CONTEXT_CHANGED", "Inspect the active app before another action")
        if (operation == "fill" && (!args.has("value") || args.optString("value").length > 10000)) return denied("INVALID_ARGUMENT", "Provide a value of at most 10000 characters")
        val executed = when (operation) {
            "click" -> node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            "fill" -> node.isEditable && args.has("value") && node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, args.getString("value")) })
            "scroll" -> node.isScrollable && node.performAction(if (args.optDouble("y", 1.0) < 0) AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
            else -> false
        }
        return JSONObject().put("executed", executed).put("verified", false).put("nextSteps", JSONArray().put("Read or inspect the resulting app state to verify the outcome"))
    }
    private fun denied(code: String, next: String): JSONObject = JSONObject().put("error", JSONObject().put("code", code).put("actionMayHaveOccurred", false).put("nextSteps", JSONArray().put(next)))
}
