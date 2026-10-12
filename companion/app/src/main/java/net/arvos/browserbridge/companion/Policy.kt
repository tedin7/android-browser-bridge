package net.arvos.browserbridge.companion

import java.net.URI

/** Pure policy functions: no Android context and no implicit target authority. */
object Policy {
    val operations = setOf("capabilities", "read", "locate", "inspect", "click", "fill", "back", "scroll")
    private val packageName = Regex("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+")
    fun packages(text: String): Set<String> {
        val values = text.split(Regex("[\\s,]+" )).filter { it.isNotBlank() }.toSet()
        require(values.size <= 32 && values.all { packageName.matches(it) }) { "Enter at most 32 exact Android package names." }
        return values
    }
    fun origin(value: String): String {
        val uri = URI(value)
        require(uri.userInfo == null && uri.fragment == null && uri.query == null && uri.path in listOf("", "/")) { "The broker URL must be an origin without credentials, query or path." }
        require(uri.host != null && uri.port in -1..65535 && uri.port != 0) { "Invalid broker address." }
        require(uri.scheme == "https" || (uri.scheme == "http" && uri.host in setOf("127.0.0.1", "localhost"))) { "Use HTTPS, or local http://127.0.0.1." }
        return value.trimEnd('/')
    }
    fun authorized(enabled: Boolean, allowed: Set<String>, foreground: String, ownPackage: String): Boolean =
        enabled && foreground in allowed && foreground != ownPackage
    fun canDecide(pendingId: String, requestId: String, decision: String, expiresAt: Long, now: Long): Boolean =
        pendingId == requestId && decision == "pending" && expiresAt > now
    fun consentStatus(checked: Boolean, previous: String): String = when {
        !checked -> "Authorization withdrawn; remote control stopped"
        previous in setOf("Explicit authorization checkbox is required", "Read and enable the authorization checkbox first", "Authorization withdrawn; remote control stopped") ->
            "Authorization selected. Tap Enable remote control when permissions are ready."
        else -> previous
    }
    fun accessibleLabel(description: CharSequence?, text: CharSequence?, hint: CharSequence?): String =
        sequenceOf(description, text, hint).mapNotNull { it?.toString() }
            .firstOrNull { it.isNotBlank() }?.take(512) ?: ""
    fun bounded(value: Int, minimum: Int, maximum: Int): Int = value.coerceIn(minimum, maximum)
}
