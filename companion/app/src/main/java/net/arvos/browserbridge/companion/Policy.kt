package net.arvos.browserbridge.companion

import java.net.URI

/** Pure policy functions: no Android context and no implicit target authority. */
object Policy {
    val operations = setOf("capabilities", "read", "locate", "inspect", "click", "fill", "back", "scroll", "foreground", "press")
    val writes = setOf("click", "fill", "scroll", "back", "press")
    private val packageName = Regex("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+")
    fun validPackage(value: String): Boolean = value.length <= 255 && packageName.matches(value)
    fun packages(text: String): Set<String> {
        val values = text.split(Regex("[\\s,]+" )).filter { it.isNotBlank() }.toSet()
        require(values.size <= 64 && values.all { validPackage(it) }) { "Enter at most 64 exact Android package names." }
        return values
    }
    fun origin(value: String): String {
        val uri = URI(value)
        require(uri.userInfo == null && uri.fragment == null && uri.query == null && uri.path in listOf("", "/")) { "The broker URL must be an origin without credentials, query or path." }
        require(uri.host != null && uri.port in -1..65535 && uri.port != 0) { "Invalid broker address." }
        require(uri.scheme == "https" || (uri.scheme == "http" && uri.host in setOf("127.0.0.1", "localhost"))) { "Use HTTPS, or local http://127.0.0.1." }
        return value.trimEnd('/')
    }
    fun authorized(enabled: Boolean, allowed: Set<String>, target: String, ownPackage: String): Boolean =
        enabled && target in allowed && target != ownPackage
    /** Permanent per-app approval chosen locally by the owner; it never extends the allowlist. */
    fun alwaysApproves(enabled: Boolean, allowed: Set<String>, always: Set<String>, target: String, ownPackage: String): Boolean =
        authorized(enabled, allowed, target, ownPackage) && target in always
    fun canDecide(pendingId: String, requestId: String, decision: String, expiresAt: Long, now: Long): Boolean =
        pendingId == requestId && decision == "pending" && expiresAt > now
    fun consentStatus(checked: Boolean, previous: String): String = when {
        !checked -> "Authorization withdrawn; remote control stopped"
        previous in setOf("Explicit authorization checkbox is required", "Read and enable the authorization checkbox first", "Authorization withdrawn; remote control stopped") ->
            "Authorization selected. Tap Enable remote control when permissions are ready."
        else -> previous
    }
    fun focusDeadline(expiresAt: Long, approvedAt: Long): Long = minOf(expiresAt, approvedAt + 5000)
    /** The approved app must still own a visible window; keyboard focus is not required (split screen). */
    fun approvedContext(enabled: Boolean, sameConnection: Boolean, allowed: Set<String>,
                        target: String, visibleTarget: String, ownPackage: String, expiresAt: Long, now: Long): Boolean =
        sameConnection && expiresAt > now && visibleTarget == target && authorized(enabled, allowed, visibleTarget, ownPackage)
    /** Labels and resource ids of a keyboard's action key (enter, search, go, done, send, next). */
    private val enterWords = setOf("enter", "invio", "search", "cerca", "go", "vai", "done", "fine", "send", "invia", "next", "avanti", "return", "↵", "⏎")
    fun isEnterKey(label: String, viewId: String?): Boolean {
        val id = viewId?.substringAfter(":id/")?.lowercase() ?: ""
        return label.trim().lowercase() in enterWords || id.contains("ime_action") || id == "key_enter" || id.endsWith("_enter")
    }
    fun accessibleLabel(description: CharSequence?, text: CharSequence?, hint: CharSequence?): String =
        sequenceOf(description, text, hint).mapNotNull { it?.toString() }
            .firstOrNull { it.isNotBlank() }?.take(512) ?: ""
    fun bounded(value: Int, minimum: Int, maximum: Int): Int = value.coerceIn(minimum, maximum)

    data class Box(val left: Int, val top: Int, val right: Int, val bottom: Int) {
        val empty get() = right <= left || bottom <= top
        fun contains(x: Int, y: Int) = x in left until right && y in top until bottom
        fun intersect(other: Box) = Box(maxOf(left, other.left), maxOf(top, other.top), minOf(right, other.right), minOf(bottom, other.bottom))
    }
    data class Window(val id: Int, val layer: Int, val bounds: Box)
    fun tapCentre(node: Box, target: Window): Pair<Int, Int>? {
        val visible = node.intersect(target.bounds)
        if (visible.empty) return null
        return Pair(visible.left + (visible.right - visible.left) / 2, visible.top + (visible.bottom - visible.top) / 2)
    }
    fun covering(point: Pair<Int, Int>, target: Window, others: List<Window>): List<Window> =
        others.filter { it.id != target.id && it.layer > target.layer && it.bounds.contains(point.first, point.second) }
    /** One node of a higher window's accessibility tree, reduced to what decides occlusion. */
    data class Content(val bounds: Box, val visible: Boolean, val interactive: Boolean, val labelled: Boolean)
    /**
     * A higher window blocks a tap only when it shows something at that point. Transparent
     * full-screen hosts such as OnePlus Open Canvas expose no labelled or interactive node there;
     * a dialog, shade, keyboard or bubble does. A window whose tree cannot be read still blocks.
     */
    fun blocks(point: Pair<Int, Int>, nodes: List<Content>?): Boolean =
        nodes == null || nodes.any { it.visible && (it.interactive || it.labelled) && it.bounds.contains(point.first, point.second) }
    /**
     * Tap point for a control without a clickable ancestor: the centre of the part of the
     * control inside its own window, refused when any higher window covers that point.
     */
    fun tapPoint(node: Box, target: Window, others: List<Window>): Pair<Int, Int>? {
        val point = tapCentre(node, target) ?: return null
        return if (covering(point, target, others).isEmpty()) point else null
    }

    /** Observable UI evidence after a write; never a claim about application semantics. */
    data class Observation(val windows: String, val tree: String, val targetState: String?, val targetText: String?)
    data class Verdict(val verified: Boolean, val effect: String)
    fun verify(operation: String, before: Observation, after: Observation?, value: String?): Verdict = when {
        after == null -> Verdict(false, "observation_unavailable")
        operation == "fill" -> if (after.targetText == value) Verdict(true, "value_matches") else Verdict(false, "value_differs")
        before.windows != after.windows -> Verdict(true, "window_changed")
        before.targetState != null && after.targetState != null && before.targetState != after.targetState -> Verdict(true, "target_state_changed")
        before.tree != after.tree -> Verdict(true, "screen_changed")
        else -> Verdict(false, "no_visible_change")
    }
}
