package net.arvos.browserbridge.companion

import android.content.Context
import android.os.SystemClock
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import java.security.KeyStore
import org.json.JSONObject

class ConnectionState(context: Context) {
    companion object { val connectionLock = Any(); private val session = SessionApproval() }
    private val ownPackage = context.packageName
    private val prefs = context.getSharedPreferences("bridge-private", Context.MODE_PRIVATE)
    var enabled: Boolean
        get() = prefs.getBoolean("enabled", false)
        set(value) = synchronized(connectionLock) { if (!value) session.clear(); prefs.edit().putBoolean("enabled", value).commit(); Unit }
    var allowed: Set<String>
        get() = prefs.getStringSet("allowed", emptySet())!!.toSet()
        set(value) = synchronized(connectionLock) {
            if (value != allowed) session.clear()
            // Permanent approval can only exist for an app that is still allowed.
            prefs.edit().putStringSet("allowed", value.toSet()).putStringSet("always", always.intersect(value)).commit(); Unit
        }
    /** Apps whose writes the owner approved permanently. Survives STOP and restarts; edited only in this app. */
    var always: Set<String>
        get() = prefs.getStringSet("always", emptySet())!!.toSet()
        set(value) = synchronized(connectionLock) { prefs.edit().putStringSet("always", value.intersect(allowed)).commit(); Unit }
    fun alwaysApproves(target: String): Boolean = Policy.alwaysApproves(enabled, allowed, always, target, ownPackage)
    var status: String
        get() = prefs.getString("status", "Not connected")!!
        set(value) { prefs.edit().putString("status", value.take(200)).commit() }
    var pending: JSONObject?
        get() = prefs.getString("pending", null)?.let { JSONObject(it) }
        set(value) { prefs.edit().putString("pending", value?.toString()).commit() }
    var approval: JSONObject?
        get() = prefs.getString("approval", null)?.let { JSONObject(it) }
        set(value) { prefs.edit().putString("approval", value?.toString()).commit() }
    fun decideApproval(id: String, approve: Boolean, forSession: Boolean = false, forever: Boolean = false) = synchronized(connectionLock) {
        val current = approval
        if (current != null && Policy.canDecide(current.optString("id"), id, current.optString("decision"), current.optLong("expiresAt"), System.currentTimeMillis())) {
            val connectionId = connection()?.optString("connectionId") ?: ""
            val target = current.optString("package")
            val authorized = approve && connectionId.isNotBlank() && current.optString("connectionId") == connectionId &&
                Policy.authorized(enabled, allowed, target, ownPackage)
            if (authorized && forSession) session.approve(target, connectionId, SystemClock.elapsedRealtime())
            if (authorized && forever) always = always + target
            current.put("session", authorized && forSession).put("always", authorized && forever)
            current.put("decision", if (authorized) "approved" else "denied")
            approval = current
        }
    }
    fun clearSession() = synchronized(connectionLock) { session.clear() }
    fun activeSession(): SessionApproval.Grant? = synchronized(connectionLock) {
        session.current(enabled, connection()?.optString("connectionId") ?: "", allowed, SystemClock.elapsedRealtime())
    }
    fun sessionAllows(target: String, connectionId: String): Boolean = synchronized(connectionLock) {
        session.permits(target, enabled && connection()?.optString("connectionId") == connectionId,
            connectionId, allowed, SystemClock.elapsedRealtime())
    }
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "browser-bridge-pairing"
        return (store.getKey(alias, null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            generateKey()
        }
    }
    fun saveConnection(value: JSONObject) = synchronized(connectionLock) {
        session.clear()
        value.put("connectionId", java.util.UUID.randomUUID().toString())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val encrypted = cipher.iv + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
        prefs.edit().putBoolean("enabled", false).putString("connection", Base64.encodeToString(encrypted, Base64.NO_WRAP)).remove("pending").remove("approval").commit()
    }
    fun connection(): JSONObject? {
        val stored = prefs.getString("connection", null) ?: return null
        val data = Base64.decode(stored, Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, data.copyOfRange(0, 12))) }
        return JSONObject(String(cipher.doFinal(data.copyOfRange(12, data.size)), Charsets.UTF_8))
    }
}
