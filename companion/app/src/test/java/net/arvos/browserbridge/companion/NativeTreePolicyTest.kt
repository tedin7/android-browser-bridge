package net.arvos.browserbridge.companion

import org.junit.Assert.*
import org.junit.Test

class NativeTreePolicyTest {
    private class Node(var value: NativeTreePolicy.Traits, var parent: Node? = null) {
        val children = mutableListOf<Node>()
        fun add(child: Node): Node { children.add(child); child.parent = this; return child }
    }
    private fun node(label: String = "", clickable: Boolean = false, packageName: String = "allowed.app", window: Int = 1,
                     visible: Boolean = true, enabled: Boolean = true, password: Boolean = false) =
        Node(NativeTreePolicy.Traits(packageName,window,visible,enabled,password,clickable,label))
    private fun resolve(node: Node) = NativeTreePolicy.clickable(node,"allowed.app",1,{it.value},{it.parent})
    private fun label(node: Node) = NativeTreePolicy.descendantLabel(node,"allowed.app",1,{it.value}) { parent, limit -> parent.children.take(limit) }
    @Test fun nearestClickableAncestorAndOwnTarget() {
        val outer=node(clickable=true); val inner=outer.add(node(clickable=true)); val leaf=inner.add(node("Browser Bridge"))
        assertSame(inner,resolve(leaf)!!.node); assertEquals(1,resolve(leaf)!!.ancestorDepth)
        assertSame(inner,resolve(inner)!!.node); assertEquals(0,resolve(inner)!!.ancestorDepth)
    }
    @Test fun resolutionNeverCrossesPackageWindowPasswordOrUnavailableState() {
        for (blocked in listOf(node(packageName="other.app"),node(window=2),node(password=true),node(visible=false),node(enabled=false))) {
            val parent=node(clickable=true); parent.add(blocked); val leaf=blocked.add(node())
            assertNull(resolve(leaf)); assertNull(resolve(blocked))
        }
    }
    @Test fun ancestorDepthIsBounded() {
        val root=node(clickable=true); var leaf=root
        repeat(4) { leaf=leaf.add(node()) }; assertEquals(4,resolve(leaf)!!.ancestorDepth)
        leaf=leaf.add(node()); assertNull(resolve(leaf))
    }
    @Test fun descendantLabelsSkipHiddenPasswordAndCrossScopeSubtrees() {
        val root=node(clickable=true); root.add(node("Browser")); root.add(node("Bridge")); root.add(node("Bridge"))
        for (hidden in listOf(node("secret",password=true),node("hidden",visible=false),node("other",packageName="other.app"),node("window",window=2))) {
            root.add(hidden).add(node("must not appear"))
        }
        assertEquals("Browser Bridge",label(root))
    }
    @Test fun labelWorkAndCharactersAreBounded() {
        val root=node(clickable=true); repeat(1000) { root.add(node("$it")) }
        val result=label(root); assertTrue(result.contains("31")); assertFalse(result.contains("32"))
        val long=node(clickable=true);long.add(node("x".repeat(10000))); assertEquals(512,label(long).length)
    }
    @Test fun descendantDepthAndChangedSemanticLabels() {
        val root=node(clickable=true); val one=root.add(node()); val two=one.add(node()); val three=two.add(node("seen"));three.add(node("too deep"))
        assertEquals("seen",label(root));three.value=three.value.copy(label="changed");assertEquals("changed",label(root))
    }
}
