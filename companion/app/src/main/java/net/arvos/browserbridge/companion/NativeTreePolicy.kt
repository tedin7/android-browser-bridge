package net.arvos.browserbridge.companion

/** Bounded tree traversal, with no Android or network dependency. */
object NativeTreePolicy {
    data class Traits(val packageName: String, val windowId: Int, val visible: Boolean,
                      val enabled: Boolean, val password: Boolean, val clickable: Boolean, val label: String = "")
    data class Resolution<T>(val node: T, val ancestorDepth: Int)
    fun inScope(value: Traits, packageName: String, windowId: Int): Boolean =
        value.packageName == packageName && value.windowId == windowId && value.visible && !value.password
    fun <T> clickable(start: T, packageName: String, windowId: Int, traits: (T) -> Traits, parent: (T) -> T?): Resolution<T>? {
        var current: T? = start
        for (depth in 0..4) {
            val node = current ?: return null
            val value = traits(node)
            if (!inScope(value, packageName, windowId) || !value.enabled) return null
            if (value.clickable) return Resolution(node, depth)
            current = parent(node)
        }
        return null
    }
    fun <T> descendantLabel(root: T, packageName: String, windowId: Int, traits: (T) -> Traits, children: (T, Int) -> List<T>): String {
        if (!inScope(traits(root), packageName, windowId)) return ""
        val queue = ArrayDeque<Pair<T, Int>>()
        children(root, 32).take(32).forEach { queue.add(it to 1) }
        val output = StringBuilder(); val seen = mutableSetOf<String>(); var visited = 0
        while (queue.isNotEmpty() && visited < 32 && output.length < 512) {
            val (node, depth) = queue.removeFirst(); visited++
            val value = traits(node)
            if (!inScope(value, packageName, windowId)) continue
            val label = value.label.trim().take(512)
            if (label.isNotEmpty() && seen.add(label)) {
                if (output.isNotEmpty()) output.append(' ')
                output.append(label.take((512 - output.length).coerceAtLeast(0)))
            }
            val remaining = 32 - visited - queue.size
            if (depth < 3 && remaining > 0) children(node, remaining).take(remaining).forEach { queue.add(it to depth + 1) }
        }
        return output.toString()
    }
}
