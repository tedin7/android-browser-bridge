package net.arvos.browserbridge.companion

import org.junit.Assert.*
import org.junit.Test

class SessionApprovalTest {
    private val allowed = setOf("org.mozilla.fenix", "other.app")
    @Test fun exactAppAndConnectionOnly() {
        val session = SessionApproval(); session.approve("org.mozilla.fenix", "connection-a", 1000)
        assertTrue(session.permits("org.mozilla.fenix", true, "connection-a", allowed, 2000))
        assertFalse(session.permits("other.app", true, "connection-a", allowed, 2000))
        assertFalse(session.permits("org.mozilla.fenix", true, "connection-b", allowed, 2000))
        assertFalse(session.permits("org.mozilla.fenix", true, "connection-a", allowed, 2000))
    }
    @Test fun expiresAtTenMinutesWithoutExtendingOnUse() {
        val session = SessionApproval(); session.approve("org.mozilla.fenix", "c", 1000)
        assertTrue(session.permits("org.mozilla.fenix", true, "c", allowed, 600999))
        assertFalse(session.permits("org.mozilla.fenix", true, "c", allowed, 601000))
        assertNull(session.current(true, "c", allowed, 2000))
    }
    @Test fun stopAndExplicitRevocationDoNotResumeWhenEnabledAgain() {
        val session = SessionApproval(); session.approve("org.mozilla.fenix", "c", 1000)
        assertFalse(session.permits("org.mozilla.fenix", false, "c", allowed, 2000))
        assertFalse(session.permits("org.mozilla.fenix", true, "c", allowed, 2000))
        session.approve("org.mozilla.fenix", "c", 3000); session.clear()
        assertFalse(session.permits("org.mozilla.fenix", true, "c", allowed, 4000))
    }
    @Test fun removedPackageAndProcessRestartDiscardGrant() {
        val session = SessionApproval(); session.approve("org.mozilla.fenix", "c", 1000)
        assertFalse(session.permits("org.mozilla.fenix", true, "c", emptySet(), 2000))
        assertFalse(session.permits("org.mozilla.fenix", true, "c", allowed, 2000))
        assertNull(SessionApproval().current(true, "c", allowed, 2000))
    }
    @Test fun invalidIdentityAndBackwardElapsedTimeFailClosed() {
        val session = SessionApproval()
        assertThrows(IllegalArgumentException::class.java) { session.approve("", "c", 1000) }
        assertThrows(IllegalArgumentException::class.java) { session.approve("org.mozilla.fenix", "", 1000) }
        session.approve("org.mozilla.fenix", "c", 1000)
        assertFalse(session.permits("org.mozilla.fenix", true, "c", allowed, 999))
    }
}
