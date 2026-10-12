package net.arvos.browserbridge.companion

import org.junit.Assert.*
import org.junit.Test

class PolicyTest {
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
}
