package net.arvos.browserbridge.companion

import org.junit.Assert.*
import org.junit.Test

class PolicyTest {
    @Test fun approvedContextRequiresOriginalAllowedFocusAndLiveConsent() {
        val allowed = setOf("org.mozilla.fenix")
        fun ready(enabled: Boolean = true, same: Boolean = true, focus: String = "org.mozilla.fenix", now: Long = 1000, packages: Set<String> = allowed) =
            Policy.approvedContext(enabled, same, packages, "org.mozilla.fenix", focus, "own.app", 30000, now)
        assertTrue(ready())
        assertFalse(ready(enabled = false))
        assertFalse(ready(same = false))
        assertFalse(ready(focus = "own.app"))
        assertFalse(ready(focus = "com.android.systemui"))
        assertFalse(ready(focus = "other.allowed", packages = allowed + "other.allowed"))
        assertFalse(ready(packages = emptySet()))
        assertFalse(ready(now = 30000))
        assertFalse(ready(now = 30001))
    }
    @Test fun returnFocusNeverExtendsOriginalApprovalExpiry() {
        assertEquals(15000L, Policy.focusDeadline(30000, 10000))
        assertEquals(30000L, Policy.focusDeadline(30000, 29000))
        assertEquals(30000L, Policy.focusDeadline(30000, 31000))
    }
    @Test fun accessibleLabelSkipsEmptyDescriptions() {
        assertEquals("Click fixture", Policy.accessibleLabel("", "Click fixture", "hint"))
        assertEquals("Click fixture", Policy.accessibleLabel("  ", "Click fixture", null))
        assertEquals("Accessible description", Policy.accessibleLabel("Accessible description", "text", "hint"))
        assertEquals("Search", Policy.accessibleLabel(null, "", "Search"))
        assertEquals("", Policy.accessibleLabel(null, " ", null))
        assertEquals(512, Policy.accessibleLabel(null, "x".repeat(600), null).length)
    }
    @Test fun consentSelectionClearsOnlyStaleConsentErrors() {
        assertEquals("Authorization withdrawn; remote control stopped", Policy.consentStatus(false,"Connected"))
        assertEquals("Authorization selected. Tap Enable remote control when permissions are ready.", Policy.consentStatus(true,"Explicit authorization checkbox is required"))
        assertEquals("Broker unavailable", Policy.consentStatus(true,"Broker unavailable"))
    }
    @Test fun controlRequiresConsentAndExactAllowlist() {
        assertFalse(Policy.authorized(false,setOf("org.example.target"),"org.example.target","own.app"))
        assertFalse(Policy.authorized(true,setOf("org.example.target"),"org.example.target.other","own.app"))
        assertFalse(Policy.authorized(true,setOf("own.app"),"own.app","own.app"))
        assertTrue(Policy.authorized(true,setOf("org.example.target"),"org.example.target","own.app"))
    }
    @Test fun approvalIsBoundToOneRequestAndExpires() {
        assertTrue(Policy.canDecide("one","one","pending",2000,1000))
        assertFalse(Policy.canDecide("one","other","pending",2000,1000))
        assertFalse(Policy.canDecide("one","one","approved",2000,1000))
        assertFalse(Policy.canDecide("one","one","denied",2000,1000))
        assertFalse(Policy.canDecide("one","one","pending",1000,1000))
    }
    @Test fun onlyHttpsOrLoopbackOrigins() {
        assertEquals("https://broker.example",Policy.origin("https://broker.example/"))
        assertEquals("http://127.0.0.1:8766",Policy.origin("http://127.0.0.1:8766"))
        for (url in listOf("http://broker.example","https://name:secret@broker.example","https://broker.example/api","https://broker.example?token=secret","file:///tmp/x")) {
            assertThrows(IllegalArgumentException::class.java) { Policy.origin(url) }
        }
    }
    @Test fun packageWildcardsAndArbitraryOperationsAreAbsent() {
        assertEquals(setOf("org.example.one","org.example.two"),Policy.packages("org.example.one\norg.example.two"))
        assertThrows(IllegalArgumentException::class.java) { Policy.packages("org.example.*") }
        assertFalse("eval" in Policy.operations)
        assertFalse("shell" in Policy.operations)
        assertFalse("screenshot" in Policy.operations)
    }
    @Test fun permanentApprovalNeedsConsentAllowlistAndOwnerChoice() {
        val allowed = setOf("org.mozilla.fenix", "com.example.mail")
        assertTrue(Policy.alwaysApproves(true, allowed, setOf("org.mozilla.fenix"), "org.mozilla.fenix", "own.app"))
        assertFalse(Policy.alwaysApproves(false, allowed, setOf("org.mozilla.fenix"), "org.mozilla.fenix", "own.app"))
        assertFalse(Policy.alwaysApproves(true, allowed, setOf("org.mozilla.fenix"), "com.example.mail", "own.app"))
        assertFalse(Policy.alwaysApproves(true, setOf("com.example.mail"), setOf("org.mozilla.fenix"), "org.mozilla.fenix", "own.app"))
        assertFalse(Policy.alwaysApproves(true, setOf("own.app"), setOf("own.app"), "own.app", "own.app"))
    }
    @Test fun splitScreenVisibilityIsEnoughWithoutFocus() {
        // The target is evaluated by its visible window, not by the focused pane.
        assertTrue(Policy.approvedContext(true, true, setOf("org.mozilla.fenix"), "org.mozilla.fenix", "org.mozilla.fenix", "own.app", 2000, 1000))
        assertFalse(Policy.approvedContext(true, true, setOf("org.mozilla.fenix"), "org.mozilla.fenix", "", "own.app", 2000, 1000))
    }
    @Test fun tapPointUsesVisibleCentreAndRefusesCoveredPoints() {
        val window = Policy.Window(1, 5, Policy.Box(0, 0, 1000, 2000))
        assertEquals(Pair(150, 60), Policy.tapPoint(Policy.Box(100, 40, 200, 80), window, listOf(window)))
        // Partly off-window: centre of the visible part only.
        assertEquals(Pair(950, 60), Policy.tapPoint(Policy.Box(900, 40, 1200, 80), window, listOf(window)))
        assertNull(Policy.tapPoint(Policy.Box(1100, 40, 1200, 80), window, listOf(window)))
        val shade = Policy.Window(2, 9, Policy.Box(0, 0, 1000, 300))
        assertNull(Policy.tapPoint(Policy.Box(100, 40, 200, 80), window, listOf(window, shade)))
        val below = Policy.Window(3, 1, Policy.Box(0, 0, 1000, 300))
        assertEquals(Pair(150, 60), Policy.tapPoint(Policy.Box(100, 40, 200, 80), window, listOf(window, below)))
    }
    @Test fun onlyHigherWindowsShowingContentAtThePointBlockTaps() {
        val point = Pair(150, 60)
        // OnePlus Open Canvas: a full-screen host window with an empty, unlabelled root.
        assertFalse(Policy.blocks(point, listOf(Policy.Content(Policy.Box(0, 0, 3392, 2400), true, false, false))))
        assertFalse(Policy.blocks(point, emptyList()))
        // Its drag handle elsewhere does not block this point.
        assertFalse(Policy.blocks(point, listOf(Policy.Content(Policy.Box(1600, 0, 1800, 40), true, true, true))))
        // A dialog button or labelled text at the point blocks; invisible nodes do not.
        assertTrue(Policy.blocks(point, listOf(Policy.Content(Policy.Box(100, 40, 200, 80), true, true, false))))
        assertTrue(Policy.blocks(point, listOf(Policy.Content(Policy.Box(0, 0, 1000, 300), true, false, true))))
        assertFalse(Policy.blocks(point, listOf(Policy.Content(Policy.Box(0, 0, 1000, 300), false, true, true))))
        // An unreadable window still blocks.
        assertTrue(Policy.blocks(point, null))
    }
    @Test fun verificationReportsObservableEvidenceOnly() {
        val before = Policy.Observation("w1", "t1", "false:false", "old")
        assertEquals(Policy.Verdict(true, "value_matches"), Policy.verify("fill", before, before.copy(targetText = "new"), "new"))
        assertEquals(Policy.Verdict(false, "value_differs"), Policy.verify("fill", before, before, "new"))
        assertEquals(Policy.Verdict(true, "window_changed"), Policy.verify("click", before, before.copy(windows = "w2"), null))
        assertEquals(Policy.Verdict(true, "target_state_changed"), Policy.verify("click", before, before.copy(targetState = "true:false"), null))
        assertEquals(Policy.Verdict(true, "screen_changed"), Policy.verify("scroll", before, before.copy(tree = "t2"), null))
        assertEquals(Policy.Verdict(false, "no_visible_change"), Policy.verify("click", before, before, null))
        assertEquals(Policy.Verdict(false, "observation_unavailable"), Policy.verify("click", before, null, null))
    }
    @Test fun foregroundIsTheOnlyNewOperation() {
        assertEquals(setOf("capabilities", "read", "locate", "inspect", "click", "fill", "back", "scroll", "foreground"), Policy.operations)
        assertFalse("foreground" in Policy.writes)
        assertTrue(Policy.validPackage("org.mozilla.fenix"))
        assertFalse(Policy.validPackage("org.mozilla.fenix;rm"))
    }
}
