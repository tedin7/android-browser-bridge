package net.arvos.browserbridge.companion

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.graphics.Path
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class BridgeAccessibilityService : AccessibilityService() {
    companion object {
        const val VERSION = "0.2.3-experimental"
        /** True while Android has this service bound in this process; the most direct evidence it is enabled. */
        val connected = AtomicBoolean(false)
    }
    private val alive = AtomicBoolean(false)
    private val main = Handler(Looper.getMainLooper())
    private lateinit var state: ConnectionState
    private val session = java.util.UUID.randomUUID().toString()
    private var epoch = 0L
    private var refCounter = 0L
    private val references = mutableMapOf<String, Pair<AccessibilityNodeInfo, String>>()
    private var worker: Thread? = null
    /** Main thread only: evidence captured just before the last write, consumed by its verification. */
    private var pendingVerification: PendingVerification? = null
    private class PendingVerification(val operation: String, val target: String, val windowId: Int, val node: AccessibilityNodeInfo?, val before: Policy.Observation, val value: String?)
    private class Target(val root: AccessibilityNodeInfo, val packageName: String, val window: AccessibilityWindowInfo?)

    override fun onServiceConnected() {
        state = ConnectionState(this)
        connected.set(true)
        // Android enabling the service is separate from the app's remote-control consent.
        if (alive.compareAndSet(false, true)) worker = Thread({ runConnection() }, "bridge-native-serial").apply { start() }
    }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) { epoch++; references.clear() }
    }
    override fun onInterrupt() { if (::state.isInitialized) { state.enabled = false; state.status = "Interrupted: control stopped" } }
    override fun onDestroy() {
        alive.set(false); connected.set(false); worker?.interrupt()
        if (::state.isInitialized) { state.enabled = false; state.status = "Accessibility service stopped" }
        ControlNotifications.cancel(getSystemService(NotificationManager::class.java))
        super.onDestroy()
    }
    private fun pause(milliseconds: Long) { try { Thread.sleep(milliseconds) } catch (_: InterruptedException) { } }
    private fun <T> onMain(timeoutMs: Long, block: () -> T): T? {
        val task = FutureTask<T> { block() }
        main.post(task)
        return try { task.get(timeoutMs.coerceAtLeast(1), TimeUnit.MILLISECONDS) } catch (_: Exception) { task.cancel(false); null }
    }
    private fun runConnection() {
        var backoff = 1000L
        while (alive.get()) {
            if (!state.enabled && state.pending == null) { ControlNotifications.cancel(getSystemService(NotificationManager::class.java)); pause(500); continue }
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
                val response = BrokerTransport.request(origin, "/api/poll", JSONObject().put("device", device).put("version", "companion-$VERSION").put("waitMs", 15000), token)
                backoff = 1000; state.status = "Connected: waiting for an authorized command"
                val command = response.optJSONObject("command") ?: continue
                val id = command.getString("id")
                val operation = command.optString("op")
                val args = command.optJSONObject("args") ?: JSONObject()
                val needsApproval = operation in Policy.writes
                val prepared = if (operation == "capabilities") null else prepareTarget(operation, args)
                val preparationFailure = prepared?.optJSONObject("error")?.let { prepared }
                val target = prepared?.optString("package") ?: ""
                val localApprovalFailure = preparationFailure ?: if (needsApproval) awaitApproval(command, connection, target) else null
                val approvalFailure = localApprovalFailure ?: if (needsApproval) authorizeAtBroker(command, connection) else null
                val task = FutureTask<JSONObject> {
                    synchronized(ConnectionState.connectionLock) {
                        if (approvalFailure != null) approvalFailure
                        else if (state.connection()?.optString("connectionId") != connection.optString("connectionId")) denied("CONNECTION_CHANGED", "This command belongs to a replaced connection; do not replay it")
                        else if (needsApproval && command.optBoolean("_always") && !state.alwaysApproves(target))
                            denied("APPROVAL_REQUIRED", "Permanent approval for this app was removed. No action was performed")
                        else if (needsApproval && command.optBoolean("_usesSession") && !state.sessionAllows(target, connection.optString("connectionId")))
                            denied("APPROVAL_REQUIRED", "The app session approval expired or was revoked. No action was performed")
                        else if (needsApproval && !Policy.approvedContext(state.enabled && alive.get(), true, state.allowed,
                            target, resolveTarget(target)?.packageName ?: "", packageName,
                            command.optLong("_approvalExpiresAt"), System.currentTimeMillis()))
                            denied("CONTEXT_CHANGED", "Approval expired or the approved app no longer has a visible window. No action was performed; inspect before another request")
                        else execute(operation, args, target.ifEmpty { null }).also { result ->
                            prepared?.optJSONObject("autoForeground")?.let { result.put("autoForeground", it) }
                        }
                    }
                }
                main.post(task)
                val payload = JSONObject().put("device", device).put("id", id)
                try {
                    val result = task.get(5, TimeUnit.SECONDS)
                    if (result.optBoolean("executed")) {
                        // Let the app react, then compare the screen with the evidence taken before the action.
                        pause(if (operation == "back") 700 else 500)
                        onMain(2000) { verifyPending(result) } ?: result.put("verified", false).put("effect", "observation_unavailable")
                    }
                    payload.put("result", result)
                }
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

    // ---- Target windows: the allowed app may be visible without keyboard focus (split screen). ----
    private fun allWindows(): List<AccessibilityWindowInfo> = try { windows ?: emptyList() } catch (_: Exception) { emptyList() }
    private fun resolveTarget(requested: String?): Target? {
        val apps = allWindows().filter { it.type == AccessibilityWindowInfo.TYPE_APPLICATION }
            .mapNotNull { window -> window.root?.let { root -> Target(root, root.packageName?.toString() ?: "", window) } }
        if (!requested.isNullOrEmpty()) return apps.firstOrNull { it.packageName == requested && it.window?.isActive == true } ?: apps.firstOrNull { it.packageName == requested }
        val active = rootInActiveWindow
        val activePackage = active?.packageName?.toString() ?: ""
        if (active != null && Policy.authorized(true, state.allowed, activePackage, packageName))
            return Target(active, activePackage, apps.firstOrNull { it.root.windowId == active.windowId }?.window)
        // Focus may sit in another split-screen pane, e.g. the terminal: use the single visible allowed app.
        val visibleAllowed = apps.filter { Policy.authorized(true, state.allowed, it.packageName, packageName) }.distinctBy { it.packageName }
        return visibleAllowed.singleOrNull()
    }
    private fun focusedPackage(): String = rootInActiveWindow?.packageName?.toString() ?: ""
    private fun launch(target: String): Boolean = try {
        val intent = packageManager.getLaunchIntentForPackage(target)
        if (intent == null) false else {
            // Same flags as the launcher: resume the existing task without clearing it.
            startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)); true
        }
    } catch (_: Exception) { false }
    /** Worker thread: choose the allowed app and bring it on screen when it is not visible. */
    private fun prepareTarget(operation: String, args: JSONObject): JSONObject {
        val requested = args.optString("package").trim()
        if (requested.isNotEmpty() && !Policy.validPackage(requested)) return denied("INVALID_ARGUMENT", "package must be an exact Android package name")
        if (requested.isNotEmpty() && !Policy.authorized(true, state.allowed, requested, packageName))
            return denied("PACKAGE_NOT_ALLOWED", "Add this app in Browser Bridge Companion (Apps) before controlling it. Do not add packages automatically.").apply {
                getJSONObject("error").put("requestedPackage", requested).put("allowedPackages", JSONArray(state.allowed.sorted()))
            }
        val visible = onMain(1000) { resolveTarget(requested.ifEmpty { null })?.packageName } ?: ""
        val candidate = requested.ifEmpty { visible.ifEmpty { state.allowed.singleOrNull() ?: "" } }
        if (candidate.isEmpty()) return denied("PACKAGE_NOT_ALLOWED", "No allowed app is visible. Pass args.package with one of allowedPackages to open it automatically.").apply {
            getJSONObject("error").put("foregroundPackage", onMain(1000) { focusedPackage() } ?: "").put("allowedPackages", JSONArray(state.allowed.sorted()))
        }
        // back is a global key: it reaches the focused window, so it needs real focus; foreground asks for it explicitly.
        val needsFocus = operation == "back" || operation == "foreground"
        val ready = { if (needsFocus) onMain(1000) { focusedPackage() } == candidate else onMain(1000) { resolveTarget(candidate)?.packageName } == candidate }
        if (ready()) return JSONObject().put("package", candidate)
        if (!launch(candidate)) return denied("FOREGROUND_FAILED", "Android provides no launcher entry for $candidate; open it manually").apply { getJSONObject("error").put("package", candidate) }
        val deadline = SystemClock.elapsedRealtime() + 4000
        while (SystemClock.elapsedRealtime() < deadline) {
            pause(150)
            if (ready()) return JSONObject().put("package", candidate).put("autoForeground", JSONObject().put("package", candidate).put("launched", true))
        }
        return denied("FOREGROUND_FAILED", "$candidate was launched but did not become ${if (needsFocus) "focused" else "visible"} within 4 seconds. Unlock the device or dismiss overlays").apply {
            getJSONObject("error").put("package", candidate).put("foregroundPackage", onMain(1000) { focusedPackage() } ?: "")
        }
    }

    private fun authorizeAtBroker(command: JSONObject, connection: JSONObject): JSONObject? {
        val remaining = command.optLong("_approvalExpiresAt") - System.currentTimeMillis()
        if (remaining <= 0) return denied("APPROVAL_REQUIRED", "Approval expired before broker authorization; no action was performed")
        return try {
            val response = BrokerTransport.request(connection.getString("url"), "/api/native-preflight",
                JSONObject().put("device", connection.getString("device")).put("id", command.getString("id")),
                connection.getString("token"), minOf(1000L, (remaining / 2).coerceAtLeast(1)).toInt())
            if (response.opt("allowed") == true) null else { state.clearSession(); denied("COMMAND_NOT_AUTHORIZED", "The broker did not authorize this pending command. No action was performed; check revocation or command expiry") }
        } catch (error: HttpFailure) {
            state.clearSession()
            if (error.status == 401 || error.status == 403) state.enabled = false
            denied("COMMAND_NOT_AUTHORIZED", "The broker rejected native preflight. No action was performed; check the connection and command status")
        } catch (_: Exception) {
            denied("BROKER_PREFLIGHT_UNAVAILABLE", "Broker authorization could not be verified. No action was performed; restore connectivity before a new request")
        }
    }
    private fun awaitApproval(command: JSONObject, connection: JSONObject, target: String): JSONObject? {
        if (!Policy.authorized(state.enabled, state.allowed, target, packageName)) return denied("PACKAGE_NOT_ALLOWED", "Open an allowed app; compare allowedPackages. Do not expand the allowlist automatically.").apply {
            getJSONObject("error").put("targetPackage", target).put("allowedPackages", JSONArray(state.allowed.sorted()))
        }
        val connectionId = connection.optString("connectionId")
        if (state.alwaysApproves(target)) {
            // Permanent approval chosen in the app; broker preflight and the final visibility check still apply.
            command.put("_approvedPackage", target).put("_approvalExpiresAt", System.currentTimeMillis() + 30000).put("_always", true)
            return null
        }
        val manager = getSystemService(NotificationManager::class.java)
        ControlNotifications.blockedReason(manager)?.let { return denied("NOTIFICATION_BLOCKED", it) }
        val expiresAt = System.currentTimeMillis() + 30000
        val approval = JSONObject().put("id", command.getString("id")).put("operation", command.optString("op"))
            .put("package", target).put("args", command.optJSONObject("args") ?: JSONObject())
            .put("expiresAt", expiresAt).put("decision", "pending").put("connectionId", connectionId)
        command.put("_approvedPackage", target).put("_approvalExpiresAt", expiresAt)
        if (state.sessionAllows(target, connectionId)) {
            command.put("_usesSession", true)
            return null // Same fixed-operation policy and broker preflight still apply.
        }
        state.approval = approval
        state.status = "Waiting for your approval: ${command.optString("op")} in $target"
        showStopNotification(approval)
        var returnDeadline: Long? = null
        try {
            while (alive.get() && state.enabled && System.currentTimeMillis() < expiresAt) {
                if (state.connection()?.optString("connectionId") != connectionId)
                    return denied("CONNECTION_CHANGED", "The connection changed; this action was not performed")
                ControlNotifications.blockedReason(manager)?.let { return denied("NOTIFICATION_BLOCKED", it) }
                when (state.approval?.optString("decision")) {
                    "approved" -> {
                        if (state.approval?.optBoolean("session") == true) {
                            command.put("_usesSession", true)
                            if (!state.sessionAllows(target, connectionId)) return denied("APPROVAL_REQUIRED", "The app session was revoked or expired; no action was performed")
                        }
                        if (state.approval?.optBoolean("always") == true) command.put("_always", true)
                        if (returnDeadline == null) {
                            returnDeadline = Policy.focusDeadline(expiresAt, System.currentTimeMillis())
                            state.status = "Approved. Returning to $target"
                            // Close the notification shade and bring the app back without user action.
                            if (Build.VERSION.SDK_INT >= 31) performGlobalAction(GLOBAL_ACTION_DISMISS_NOTIFICATION_SHADE)
                            if (onMain(1000) { resolveTarget(target)?.packageName } != target) launch(target)
                        }
                        val now = System.currentTimeMillis()
                        if (now >= returnDeadline) return denied("CONTEXT_CHANGED", "The approved app did not become visible again before the return deadline. No action was performed")
                        val visible = onMain(minOf(1000, returnDeadline - now)) { resolveTarget(target)?.packageName }
                        if (visible != null && Policy.approvedContext(state.enabled && alive.get(),
                                state.connection()?.optString("connectionId") == connectionId,
                                state.allowed, target, visible, packageName, expiresAt, System.currentTimeMillis())) return null
                    }
                    "denied", null -> return denied("APPROVAL_REQUIRED", "Approval was denied or cleared; no action was performed")
                }
                pause(100)
            }
            return denied("APPROVAL_REQUIRED", "Approval expired or control stopped; no action was performed. Approve from the notification, or enable Always approve for this app in Browser Bridge Companion")
        } finally { state.approval = null; manager.cancel(2); showStopNotification() }
    }
    private fun showStopNotification(approval: JSONObject? = null) {
        val manager = getSystemService(NotificationManager::class.java)
        if (!state.enabled) { ControlNotifications.cancel(manager); return }
        ControlNotifications.blockedReason(manager)?.let { state.enabled = false; state.status = it; ControlNotifications.cancel(manager); return }
        val stop = PendingIntent.getBroadcast(this, 1, Intent(this, StopReceiver::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 2, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        try {
            val always = state.always.size
            val notification = Notification.Builder(this, if (approval == null) ControlNotifications.CONTROL else ControlNotifications.APPROVAL).setSmallIcon(android.R.drawable.ic_menu_view)
                .setContentTitle(if (approval == null) "Browser Bridge: controllo attivo" else "Approvare ${approval.optString("operation")} in ${appLabel(approval.optString("package"))}?")
                .setContentText(if (approval == null) state.activeSession()?.let { "Sessione: ${appLabel(it.target)}. STOP revoca tutto." }
                    ?: "${state.allowed.size} app consentite, $always con approvazione permanente. STOP per fermare."
                    else "Una volta, 10 minuti, o sempre per questa app. Scade in 30 secondi.")
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .setContentIntent(open).setAutoCancel(false).setOngoing(true).addAction(Notification.Action.Builder(null, "STOP", stop).build())
            if (approval != null) {
                notification.setStyle(Notification.BigTextStyle().bigText("Argomenti richiesti: " + (approval.optJSONObject("args") ?: JSONObject()).toString().take(12000)))
                for ((request, mode) in listOf(3 to "once", 5 to "session", 6 to "always")) {
                    val decision = PendingIntent.getBroadcast(this, request, Intent(this, ApprovalReceiver::class.java)
                        .putExtra("id", approval.getString("id")).putExtra("approve", true).putExtra("session", mode == "session").putExtra("always", mode == "always"),
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                    notification.addAction(Notification.Action.Builder(null, when (mode) { "session" -> "10 min"; "always" -> "Sempre"; else -> "Una volta" }, decision).build())
                }
            }
            manager.notify(if (approval == null) 1 else 2, notification.build())
        } catch (_: SecurityException) { state.enabled = false; state.status = "Allow notifications to keep a visible STOP control" }
    }
    private fun appLabel(target: String): String = try {
        packageManager.getApplicationLabel(packageManager.getApplicationInfo(target, 0)).toString()
    } catch (_: Exception) { target }

    // ---- Observation and evidence ----
    private fun fingerprint(node: AccessibilityNodeInfo): String = JSONArray(listOf(node.windowId, node.packageName?.toString(), node.viewIdResourceName, node.className?.toString(), node.text?.toString(), node.contentDescription?.toString(), role(node), label(node))).toString()
    private fun role(node: AccessibilityNodeInfo): String = when {
        node.isEditable -> "textbox"
        node.isCheckable -> "checkbox"
        node.isClickable -> "button"
        else -> "element"
    }
    private fun traits(node: AccessibilityNodeInfo) = NativeTreePolicy.Traits(
        node.packageName?.toString() ?: "", node.windowId, node.isVisibleToUser, node.isEnabled,
        node.isPassword, node.isClickable, if (node.isPassword || !node.isVisibleToUser) "" else Policy.accessibleLabel(node.contentDescription, node.text, node.hintText))
    private fun label(node: AccessibilityNodeInfo): String {
        if (node.isPassword || !node.isVisibleToUser) return ""
        val direct = Policy.accessibleLabel(node.contentDescription, node.text, node.hintText)
        if (direct.isNotEmpty() || (!node.isClickable && !node.isCheckable)) return direct
        return NativeTreePolicy.descendantLabel(node, node.packageName?.toString() ?: "", node.windowId, ::traits) { parent, limit ->
            (0 until minOf(parent.childCount, limit)).mapNotNull { parent.getChild(it) }
        }
    }
    private fun descriptor(node: AccessibilityNodeInfo): JSONObject {
        val ref = "native-$session-$epoch-${++refCounter}"
        if (references.size >= 1000) references.clear()
        references[ref] = Pair(AccessibilityNodeInfo.obtain(node), fingerprint(node))
        val bounds = Rect(); node.getBoundsInScreen(bounds)
        val result = JSONObject().put("ref", ref).put("role", role(node)).put("accessibleName", label(node)).put("visible", node.isVisibleToUser).put("enabled", node.isEnabled)
            .put("value", if (node.isPassword || !node.isEditable) JSONObject.NULL else node.text?.toString()?.take(2000) ?: "")
            .put("rect", JSONObject().put("x", bounds.left.coerceIn(-100000,100000)).put("y", bounds.top.coerceIn(-100000,100000))
                .put("width", (bounds.right.toLong() - bounds.left).coerceIn(0,100000)).put("height", (bounds.bottom.toLong() - bounds.top).coerceIn(0,100000)))
        if (node.isCheckable) result.put("checked", node.isChecked)
        if (!node.isClickable && !node.isEditable) result.put("tapFallback", true)
        return result
    }
    private fun box(rect: Rect) = Policy.Box(rect.left, rect.top, rect.right, rect.bottom)
    private fun windowBox(window: AccessibilityWindowInfo) = Rect().also { window.getBoundsInScreen(it) }.let { box(it) }
    private fun observe(target: String, windowId: Int, node: AccessibilityNodeInfo?): Policy.Observation? {
        val windows = allWindows().filter { it.type == AccessibilityWindowInfo.TYPE_APPLICATION }
        val signature = windows.joinToString("|") { "${it.id}:${it.root?.packageName}:${it.title}" }
        val root = windows.firstOrNull { it.id == windowId }?.root ?: resolveTarget(target)?.root ?: return null
        val tree = StringBuilder()
        val queue = ArrayDeque<AccessibilityNodeInfo>(); queue.add(root); var count = 0
        val bounds = Rect()
        while (queue.isNotEmpty() && count < 1000) {
            val current = queue.removeFirst(); count++
            current.getBoundsInScreen(bounds)
            tree.append(current.className).append('|').append(if (current.isPassword) "" else current.text).append('|').append(current.contentDescription)
                .append('|').append(current.isChecked).append(current.isSelected).append(current.isEnabled).append('|').append(bounds.toShortString()).append('\n')
            for (i in 0 until current.childCount) current.getChild(i)?.let { queue.add(it) }
        }
        val present = node?.refresh() == true
        val targetState = if (present) "${node!!.isChecked}:${node.isSelected}:${node.isFocused}:${node.isEnabled}" else null
        val targetText = if (present && !node!!.isPassword) node.text?.toString() ?: "" else null
        return Policy.Observation(signature, Integer.toHexString(tree.toString().hashCode()) + ":" + tree.length, targetState, targetText)
    }
    private fun verifyPending(result: JSONObject): JSONObject {
        val pending = pendingVerification ?: return result.put("verified", false).put("effect", "observation_unavailable")
        pendingVerification = null
        val after = observe(pending.target, pending.windowId, pending.node)
        val verdict = Policy.verify(pending.operation, pending.before, after, pending.value)
        result.put("verified", verdict.verified).put("effect", verdict.effect)
            .put("verification", JSONObject().put("method", "accessibility_tree_comparison").put("delayMs", if (pending.operation == "back") 700 else 500)
                .put("meaning", if (pending.operation == "fill") "The control now holds exactly the requested value" else "The app's visible state changed after the action; confirm task-specific outcomes with read"))
        result.put("nextSteps", JSONArray().put(if (verdict.verified) "Read the app only if the task needs its new content" else "No visible change was observed. Read the app before deciding whether to repeat; the action may have had a delayed or invisible effect"))
        return result
    }
    /** Nodes of a higher window that contain [point]; null when the tree is unreadable or too large. */
    private fun contentAt(window: AccessibilityWindowInfo, point: Pair<Int, Int>): List<Policy.Content>? {
        val root = window.root ?: return null
        val found = mutableListOf<Policy.Content>()
        val queue = ArrayDeque(listOf(root))
        var seen = 0
        while (queue.isNotEmpty()) {
            if (++seen > 3000) return null
            val node = queue.removeFirst()
            val bounds = Rect(); node.getBoundsInScreen(bounds)
            val box = box(bounds)
            if (box.contains(point.first, point.second)) found += Policy.Content(box, node.isVisibleToUser,
                node.isClickable || node.isLongClickable || node.isFocusable || node.isEditable || node.isCheckable,
                !node.text.isNullOrBlank() || !node.contentDescription.isNullOrBlank())
            for (index in 0 until node.childCount) node.getChild(index)?.let(queue::addLast)
        }
        return found
    }
    /** Returns the tapped point, or fills [problem] with why no tap was sent. */
    private fun tap(node: AccessibilityNodeInfo, window: AccessibilityWindowInfo?, problem: JSONObject): Pair<Int, Int>? {
        if (window == null) { problem.put("reason", "target_window_unknown"); return null }
        val bounds = Rect(); node.getBoundsInScreen(bounds)
        val target = Policy.Window(window.id, window.layer, windowBox(window))
        val point = Policy.tapCentre(box(bounds), target) ?: run { problem.put("reason", "off_window"); return null }
        val all = allWindows()
        val covering = Policy.covering(point, target, all.map { Policy.Window(it.id, it.layer, windowBox(it)) })
            .filter { cover -> Policy.blocks(point, contentAt(all.first { it.id == cover.id }, point)) }
        if (covering.isNotEmpty()) {
            problem.put("reason", "covered").put("coveringWindows", JSONArray(covering.map { cover ->
                val info = all.first { it.id == cover.id }
                JSONObject().put("type", info.type).put("layer", info.layer).put("title", info.title?.toString()?.take(80) ?: JSONObject.NULL)
                    .put("package", info.root?.packageName?.toString() ?: JSONObject.NULL).put("bounds", Rect().also { info.getBoundsInScreen(it) }.toShortString())
            })).put("targetLayer", window.layer)
            return null
        }
        val path = Path().apply { moveTo(point.first.toFloat(), point.second.toFloat()) }
        val gesture = GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 60)).build()
        if (!dispatchGesture(gesture, null, null)) { problem.put("reason", "gesture_rejected_by_android"); return null }
        return point
    }

    private fun execute(operation: String, args: JSONObject, requested: String?): JSONObject {
        if (!state.enabled) return denied("CONTROL_DISABLED", "Enable remote control in the companion first")
        if (operation !in Policy.operations) return denied("UNSUPPORTED_OPERATION", "Use the companion capabilities operation; browser and native capabilities differ")
        val allowedPackages = JSONArray(state.allowed.sorted())
        if (operation == "capabilities") {
            val sessionGrant = state.activeSession()
            return JSONObject().put("version", VERSION).put("backend", "android-accessibility")
                .put("foregroundPackage", focusedPackage()).put("visibleAllowedPackages", JSONArray(allWindows().filter { it.type == AccessibilityWindowInfo.TYPE_APPLICATION }
                    .mapNotNull { it.root?.packageName?.toString() }.filter { it in state.allowed }.distinct()))
                .put("allowedPackages", allowedPackages).put("alwaysApprovedPackages", JSONArray(state.always.sorted()))
                .put("operations", JSONArray(Policy.operations.sorted())).put("nativeAndroidUI", true).put("browserTabs", false).put("screenshots", false).put("trustedEvents", false).put("targetedRead", false).put("allowlistedPackages", true)
                .put("approvalRequiredForWrites", true).put("permanentAppApproval", JSONObject().put("scope", "owner-selected allowed apps on this device").put("editableRemotely", false))
                .put("appSessionApproval", JSONObject().put("maxSeconds", 600).put("scope", "exact package and connection").put("persistent", false).put("active", sessionGrant != null).put("targetPackage", sessionGrant?.target ?: JSONObject.NULL).put("remainingSeconds", sessionGrant?.let { ((it.expiresAtElapsed - SystemClock.elapsedRealtime()).coerceAtLeast(0) + 999) / 1000 } ?: 0))
                .put("targetSelection", "args.package, else the focused allowed app, else the only visible allowed app (split screen)")
                .put("autoForeground", true).put("tapFallback", true).put("postActionVerification", true).put("workflowLeases", false)
                .put("limits", JSONObject().put("maxNodes",1000).put("maxElements",50).put("textLimit",4000).put("shareBytes",1048576))
        }
        val target = resolveTarget(requested) ?: return denied("NO_ALLOWED_WINDOW", "No allowed app is visible. Pass args.package to open one automatically").apply {
            getJSONObject("error").put("foregroundPackage", focusedPackage()).put("allowedPackages", allowedPackages)
        }
        val root = target.root; val current = target.packageName
        if (!Policy.authorized(state.enabled, state.allowed, current, packageName)) return denied("PACKAGE_NOT_ALLOWED", "The target window belongs to an app outside allowedPackages. Do not add packages automatically.").apply {
            getJSONObject("error").put("targetPackage", current).put("allowedPackages", allowedPackages)
        }
        if (operation == "foreground") return JSONObject().put("package", current).put("visible", true).put("focused", focusedPackage() == current)
        if (args.has("selector") || args.has("frameId") || args.has("tabId")) return denied("UNSUPPORTED_TARGET", "Native controls use ref/name/role/label/textQuery, not CSS selectors, frames or browser tab IDs")
        if (operation == "back") {
            if (focusedPackage() != current) return denied("CONTEXT_CHANGED", "Back reaches the focused app only; $current lost focus. No action was performed")
            val before = observe(current, root.windowId, null)
            val executed = performGlobalAction(GLOBAL_ACTION_BACK)
            if (executed && before != null) pendingVerification = PendingVerification(operation, current, root.windowId, null, before, null)
            return JSONObject().put("executed", executed).put("package", current).put("verified", false)
        }
        if (operation == "press") return pressEnter(args, current, root)
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
                if (node.packageName?.toString() != current || node.windowId != root.windowId || node.isPassword || !node.isVisibleToUser) continue
                val value = node.text ?: continue
                if (observedText.isNotEmpty()) observedText.append('\n')
                val remaining = (limit + 1 - observedText.length).coerceAtLeast(0)
                observedText.append(value.subSequence(0, minOf(value.length, remaining)))
                if (observedText.length > limit || value.length > remaining) { textTruncated = true; break }
            }
            val text = observedText.toString()
            val controls = nodes.filter { it.packageName?.toString() == current && it.windowId == root.windowId && it.isVisibleToUser && !it.isPassword && (it.isClickable || it.isCheckable || it.isEditable || it.isScrollable) }
            val max = Policy.bounded(args.optInt("maxElements", 20), 0, 50)
            return JSONObject().put("backend", "android-accessibility").put("package", current).put("focused", focusedPackage() == current).put("documentId", "native-$session-$epoch")
                .put("complete", complete).put("text", text.take(limit)).put("textLength", text.length).put("textLengthExact", !textTruncated && complete).put("textTruncated", textTruncated || !complete)
                .put("elementCount", controls.size).put("truncated", controls.size > max || !complete)
                .put("elements", JSONArray(controls.take(max).map { descriptor(it) }))
        }
        val ref = args.optString("ref")
        val matches = if (ref.isNotEmpty()) {
            val recorded = references[ref] ?: return denied("STALE_REFERENCE", "Locate the control again before acting")
            if (!recorded.first.refresh() || fingerprint(recorded.first) != recorded.second || recorded.first.packageName?.toString() != current || recorded.first.windowId != root.windowId) return denied("STALE_REFERENCE", "The control changed; locate and inspect it again")
            listOf(recorded.first)
        } else nodes.filter { node ->
            val exact = args.optBoolean("exact", true)
            fun match(key: String, actual: String): Boolean = !args.has(key) || if (exact) actual == args.getString(key) else actual.contains(args.getString(key), ignoreCase = true)
            node.packageName?.toString() == current && node.windowId == root.windowId && node.isVisibleToUser && !node.isPassword && match("name", if (args.has("name")) label(node) else "") && match("label", if (args.has("label")) label(node) else "") && match("textQuery", node.text?.toString() ?: "") && match("role", role(node))
        }
        if (operation == "locate") return JSONObject().put("package", current).put("elements", JSONArray(matches.filter { !it.isPassword }.take(Policy.bounded(args.optInt("maxElements",20),0,50)).map { descriptor(it) })).put("count", matches.size).put("complete", complete)
        if (!complete && ref.isEmpty()) return denied("OBSERVATION_INCOMPLETE", "Use a confirmed ref from a targeted observation")
        if (matches.isEmpty()) return denied("TARGET_NOT_FOUND", "No control matched. Locate the current app controls and use an observed name, role or ref")
        if (matches.size != 1) return denied("TARGET_NOT_UNIQUE", "Locate one exact control and use its ref")
        val node = matches.single()
        if (node.packageName?.toString() != current || node.windowId != root.windowId || node.isPassword || !node.isVisibleToUser || !node.isEnabled) return denied("TARGET_UNAVAILABLE", "Choose a visible enabled non-password control")
        if (operation == "inspect") return descriptor(node)
        if ((operation == "fill" && !node.isEditable) || (operation == "scroll" && !node.isScrollable))
            return denied("TARGET_NOT_ACTIONABLE", "The matched control does not support this action; inspect another control").apply {
                getJSONObject("error").put("actionability", "unsupported_target_action").put("resolvedAncestor", false)
            }
        val originalFingerprint = fingerprint(node)
        // force:true asks for a screen tap at the control even when an accessibility click exists.
        val forceTap = operation == "click" && args.optBoolean("force", false)
        val resolution = if (operation == "click" && !forceTap) NativeTreePolicy.clickable(node, current, root.windowId, ::traits) { it.parent } else null
        val actionNode = resolution?.node ?: node
        val actionFingerprint = fingerprint(actionNode)
        if (!node.refresh() || fingerprint(node) != originalFingerprint || !actionNode.refresh() || fingerprint(actionNode) != actionFingerprint ||
            !NativeTreePolicy.inScope(traits(actionNode), current, root.windowId) || !actionNode.isEnabled)
            return denied("STALE_REFERENCE", "The matched or resolved control changed before action; observe again")
        if (resolution != null) {
            val refreshed = NativeTreePolicy.clickable(node, current, root.windowId, ::traits) { it.parent }
            if (refreshed == null || refreshed.node != actionNode || refreshed.ancestorDepth != resolution.ancestorDepth)
                return denied("STALE_REFERENCE", "The clickable ancestor changed; observe the control again")
        }
        // Recheck consent and that the same window is still on screen immediately before a write.
        val recheck = resolveTarget(current)
        if (recheck == null || recheck.root.windowId != root.windowId || !Policy.authorized(state.enabled, state.allowed, recheck.packageName, packageName)) return denied("CONTEXT_CHANGED", "Inspect the app before another action")
        if (operation == "fill" && (!args.has("value") || args.optString("value").length > 10000)) return denied("INVALID_ARGUMENT", "Provide a value of at most 10000 characters")
        val before = observe(current, root.windowId, node)
        var tapped: Pair<Int, Int>? = null
        val tapProblem = JSONObject()
        val executed = when (operation) {
            "click" -> if (resolution != null) actionNode.isClickable && actionNode.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                else { tapped = tap(node, recheck.window, tapProblem); tapped != null }
            "fill" -> node.isEditable && args.has("value") && node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, args.getString("value")) })
            "scroll" -> node.isScrollable && node.performAction(if (args.optDouble("y", 1.0) < 0) AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
            else -> false
        }
        if (operation == "click" && resolution == null && !executed) return denied("TARGET_NOT_ACTIONABLE", "The control has no clickable ancestor and its centre is covered or off screen. Scroll it into view or dismiss the overlay; for Firefox tabs use the browser device's tabs/foreground operations").apply {
            getJSONObject("error").put("actionability", "tap_point_unavailable").put("resolvedAncestor", false).put("tap", tapProblem)
        }
        if (!executed) return denied("ACTION_NOT_EXECUTED", "Android did not report performing the action. Inspect the current control before another request").apply {
            getJSONObject("error").put("actionMayHaveOccurred", true).put("actionability", "platform_action_returned_false")
                .put("resolvedAncestor", (resolution?.ancestorDepth ?: 0) > 0)
        }
        if (before != null) pendingVerification = PendingVerification(operation, current, root.windowId, node, before, if (operation == "fill") args.getString("value") else null)
        val result = JSONObject().put("executed", true).put("package", current).put("method", if (tapped != null) "screen_tap" else "accessibility_action")
            .put("resolvedAncestor", (resolution?.ancestorDepth ?: 0) > 0).put("ancestorDepth", resolution?.ancestorDepth ?: 0).put("verified", false)
        tapped?.let { result.put("tapPoint", JSONObject().put("x", it.first).put("y", it.second)) }
        return result
    }
    /**
     * Enter for the field that has input focus in the allowed app. Pages that ignore synthetic
     * key events (Search Console's URL box) accept the keyboard's own action: first the editor
     * action Android 11+ exposes to accessibility, then (force:true, or when that action is
     * unavailable) a real tap on the on-screen keyboard's action key.
     */
    private fun pressEnter(args: JSONObject, current: String, root: AccessibilityNodeInfo): JSONObject {
        if (args.optString("key", "Enter") != "Enter") return denied("INVALID_ARGUMENT", "The native companion presses only key Enter")
        if (focusedPackage() != current) return denied("CONTEXT_CHANGED", "Enter reaches the focused app only; $current is not focused. No action was performed")
        val input = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (input == null || input.packageName?.toString() != current || !input.isEditable || input.isPassword || !input.isVisibleToUser)
            return denied("TARGET_NOT_FOUND", "No editable field has input focus in $current. Tap the field (or fill it) first")
        val before = observe(current, root.windowId, input)
        val imeActionId = if (Build.VERSION.SDK_INT >= 30) AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id else null
        val supportsAction = imeActionId != null && input.actionList.any { it.id == imeActionId }
        var method = "ime_enter_action"
        var tapped: Pair<Int, Int>? = null
        val problem = JSONObject()
        val executed = if (supportsAction && !args.optBoolean("force", false)) input.performAction(imeActionId!!) else {
            method = "keyboard_tap"
            val keyboard = allWindows().firstOrNull { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            val key = keyboard?.root?.let { keyboardRoot ->
                val queue = ArrayDeque(listOf(keyboardRoot)); var found: AccessibilityNodeInfo? = null; var seen = 0
                while (queue.isNotEmpty() && found == null && ++seen < 2000) {
                    val node = queue.removeFirst()
                    if (node.isVisibleToUser && Policy.isEnterKey(label(node), node.viewIdResourceName)) found = node
                    for (i in 0 until node.childCount) node.getChild(i)?.let(queue::addLast)
                }
                found
            }
            if (keyboard == null) problem.put("reason", "keyboard_not_visible")
            else if (key == null) problem.put("reason", "enter_key_not_found")
            else tapped = tap(key, keyboard, problem)
            tapped != null
        }
        if (!executed) return denied("ACTION_NOT_EXECUTED", if (method == "keyboard_tap") "Tap the field so the on-screen keyboard opens, then press Enter again" else "Android did not perform the editor action; retry with force:true to tap the keyboard's Enter key").apply {
            getJSONObject("error").put("method", method).put("keyboard", problem)
        }
        if (before != null) pendingVerification = PendingVerification("press", current, root.windowId, input, before, null)
        val result = JSONObject().put("executed", true).put("package", current).put("method", method).put("verified", false)
        tapped?.let { result.put("tapPoint", JSONObject().put("x", it.first).put("y", it.second)) }
        return result
    }
    private fun denied(code: String, next: String): JSONObject = JSONObject().put("error", JSONObject().put("code", code).put("actionMayHaveOccurred", false).put("nextSteps", JSONArray().put(next)))
}
