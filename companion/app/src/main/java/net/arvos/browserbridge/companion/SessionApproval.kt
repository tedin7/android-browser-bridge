package net.arvos.browserbridge.companion

/** Process memory only. All times supplied by the caller use elapsedRealtime. */
class SessionApproval {
    data class Grant(val target: String, val connectionId: String, val expiresAtElapsed: Long)
    private var grant: Grant? = null
    @Synchronized fun approve(target: String, connectionId: String, nowElapsed: Long) {
        require(target.isNotBlank() && connectionId.isNotBlank() && nowElapsed >= 0)
        grant = Grant(target, connectionId, nowElapsed + 600000)
    }
    @Synchronized fun clear() { grant = null }
    @Synchronized fun current(enabled: Boolean, connectionId: String, allowed: Set<String>, nowElapsed: Long): Grant? {
        val value = grant ?: return null
        if (!enabled || connectionId != value.connectionId || value.target !in allowed || nowElapsed >= value.expiresAtElapsed || nowElapsed < value.expiresAtElapsed - 600000) {
            grant = null; return null
        }
        return value
    }
    @Synchronized fun permits(target: String, enabled: Boolean, connectionId: String, allowed: Set<String>, nowElapsed: Long): Boolean =
        current(enabled, connectionId, allowed, nowElapsed)?.target == target
}
