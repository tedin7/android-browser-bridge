package net.arvos.browserbridge.companion

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityManager
import android.os.Build
import android.net.Uri
import android.provider.OpenableColumns
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Base64
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject

class MainActivity : Activity() {
    private lateinit var state: ConnectionState
    private lateinit var status: TextView
    private lateinit var approvalDetails: TextView
    private lateinit var permissionStatus: TextView
    private lateinit var sharePreview: TextView
    private lateinit var shareText: EditText
    private var selectedFile: ByteArray? = null
    private var selectedName = "shared-file"
    private var selectedMime = "application/octet-stream"
    private var lastShareBody: String? = null
    private var lastShareId: String? = null
    private val handler = Handler(Looper.getMainLooper())
    private val refresh = object : Runnable {
        override fun run() {
            status.text = state.status + if (state.enabled) "\nRemote control: enabled" else "\nRemote control: stopped"
            permissionStatus.text = "Android Accessibility service: " + (if (accessibilityEnabled()) "enabled" else "disabled — open Accessibility settings") +
                "\nSTOP notification permission: " + (if (notificationsEnabled()) "allowed" else "blocked — allow notifications")
            approvalDetails.text = state.approval?.let { "Pending approval: " + it.optString("operation") + " in " + it.optString("package") + "\n" + (it.optJSONObject("args") ?: JSONObject()).toString() } ?: "No action awaiting approval"
            handler.postDelayed(this, 1000)
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        state = ConnectionState(this)
        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32,32,32,32) }
        fun text(value: String) = TextView(this).also { it.text = value; column.addView(it) }
        fun button(value: String, action: () -> Unit) = Button(this).also { it.text = value; it.setOnClickListener { action() }; column.addView(it) }
        text("Browser Bridge Companion · experimental")
        text("Optional native app control. Your paired server can read visible app text and click or fill accessible controls only in the packages you allow, while enabled. Password fields are excluded. This is independent of your Firefox connection.")
        status = text(state.status)
        permissionStatus = text("")
        val pairing = EditText(this).apply { hint = "Paste BB1 pairing string for a NEW native device"; setSingleLine(false) }; column.addView(pairing)
        val packages = EditText(this).apply { hint = "Allowed Android package names, one per line"; setText(state.allowed.sorted().joinToString("\n")) }; column.addView(packages)
        val consent = CheckBox(this).apply {
            text = "I authorize this server to read and control the listed apps when enabled"
            isChecked = state.enabled
        }; column.addView(consent)
        consent.setOnCheckedChangeListener { _, checked ->
            if (!checked) {
                state.enabled = false; state.approval = null
                getSystemService(NotificationManager::class.java).cancel(1)
            }
            state.status = Policy.consentStatus(checked, state.status)
            status.text = state.status + if (state.enabled) "\nRemote control: enabled" else "\nRemote control: stopped"
        }
        button("Pair server") {
            try {
                require(consent.isChecked) { "Read and enable the authorization checkbox first" }
                val allowed = Policy.packages(packages.text.toString())
                require(allowed.isNotEmpty()) { "Add at least one app package" }
                val encoded = pairing.text.toString().trim()
                require(encoded.startsWith("BB1.") && encoded.length <= 8192) { "Paste a valid BB1 pairing string" }
                val data = JSONObject(String(Base64.decode(encoded.substring(4), Base64.URL_SAFE or Base64.NO_WRAP), Charsets.UTF_8))
                val origin = Policy.origin(data.getString("url")); val code = data.getString("code")
                require(code.length in 1..128) { "Invalid pairing code" }
                state.enabled = false; state.status = "Pairing…"
                Thread {
                    try {
                        // Pairing is one-use: never automatically retry a lost response.
                        val result = BrokerTransport.request(origin,"/api/pair",JSONObject().put("code",code))
                        result.put("url",origin)
                        require(result.getString("token").isNotBlank() && result.getString("device").isNotBlank())
                        state.saveConnection(result); state.allowed = allowed; state.status = "Paired. Enable Android Accessibility, then enable control here."
                        runOnUiThread { pairing.setText("") }
                    } catch (_: Exception) { state.status = "Pairing not confirmed. Check connection; create a new enrollment before retrying." }
                }.start()
            } catch (error: Exception) { state.status = error.message?.take(160) ?: "Invalid pairing settings" }
        }
        button("Open Android Accessibility settings") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        button("Allow STOP notification") {
            if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),1)
            else startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE,packageName))
        }
        button("Enable remote control") {
            try {
                require(consent.isChecked) { "Explicit authorization checkbox is required" }
                val allowed=Policy.packages(packages.text.toString())
                require(allowed.isNotEmpty() && packageName !in allowed) { "Allow at least one target app, excluding this companion" }
                require(state.connection()!=null) { "Pair a server first" }
                require(accessibilityEnabled()) { "Enable Browser Bridge Companion in Android Accessibility settings, return here, then tap Enable remote control" }
                require(notificationsEnabled()) { "Allow notifications so STOP stays visible" }
                state.allowed=allowed; state.enabled=true; state.status="Enabled; waiting for the Accessibility service connection"
            } catch (error: Exception) { state.status=error.message?.take(160) ?: "Cannot enable control" }
        }
        button("STOP REMOTE CONTROL") {
            state.enabled=false; state.status="Stopped locally"
            getSystemService(NotificationManager::class.java).cancel(1)
        }
        approvalDetails = text("No action awaiting approval")
        button("Approve this action once") {
            state.approval?.let { state.decideApproval(it.getString("id"),true) }
            // Return to the previous app. Ref freshness is still checked; no
            // cached target is silently rebound after reviewing this screen.
            finish()
        }
        button("Deny this action") { state.approval?.let { state.decideApproval(it.getString("id"),false) } }
        text("Explicit share to paired server (independent of native control)")
        shareText = EditText(this).apply { hint = "Text or URL to share" }; column.addView(shareText)
        sharePreview = text("No file selected. Nothing is sent automatically.")
        button("Choose one file (up to 1 MiB)") {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"), 20)
        }
        button("Clear file; share text instead") { selectedFile=null; sharePreview.text="No file selected" }
        button("Review and send to paired server") { reviewShare() }
        if (intent.action == Intent.ACTION_SEND) {
            intent.getStringExtra(Intent.EXTRA_TEXT)?.let { shareText.setText(it.take(65536)) }
            @Suppress("DEPRECATION")
            val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
            if (uri != null) loadFile(uri)
        }
        setContentView(ScrollView(this).apply { addView(column,ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT)) })
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode,resultCode,data)
        if (requestCode==20 && resultCode==RESULT_OK) data?.data?.let { loadFile(it) }
    }
    private fun loadFile(uri: Uri) {
        if (uri.scheme != "content") { state.status="Choose a file through Android's document picker"; return }
        Thread {
            try {
                val name = contentResolver.query(uri,arrayOf(OpenableColumns.DISPLAY_NAME),null,null,null)?.use { cursor ->
                    if (cursor.moveToFirst()) cursor.getString(0).take(128) else "shared-file"
                } ?: "shared-file"
                val mime = contentResolver.getType(uri) ?: "application/octet-stream"
                val bytes = contentResolver.openInputStream(uri)?.use { input ->
                    val output = java.io.ByteArrayOutputStream(); val buffer=ByteArray(8192)
                    while (output.size()<=1048576) {
                        val count=input.read(buffer,0,minOf(buffer.size,1048577-output.size()))
                        if (count<0) break
                        output.write(buffer,0,count)
                    }
                    output.toByteArray()
                } ?: throw IllegalArgumentException("Cannot open file")
                require(bytes.size<=1048576) { "File exceeds 1 MiB" }
                runOnUiThread { selectedFile=bytes; selectedName=name; selectedMime=mime; sharePreview.text="Ready to review: $name ($mime, ${bytes.size} bytes). Not sent." }
            } catch (_: Exception) { state.status="File unavailable or exceeds 1 MiB; nothing sent" }
        }.start()
    }
    private fun reviewShare() {
        try {
            val connection=state.connection() ?: throw IllegalArgumentException("Pair a server first")
            val body=JSONObject().put("device",connection.getString("device"))
            val file=selectedFile
            val preview = if (file!=null) {
                body.put("mimeType",selectedMime).put("name",selectedName).put("dataBase64",Base64.encodeToString(file,Base64.NO_WRAP))
                "$selectedName ($selectedMime, ${file.size} bytes)"
            } else {
                val value=shareText.text.toString()
                require(value.isNotEmpty() && value.toByteArray(Charsets.UTF_8).size<=65536) { "Enter text or URL up to 64 KiB" }
                body.put("mimeType","text/plain").put("name","shared-text.txt").put("text",value)
                value.take(1000) + if (value.length>1000) "\n[Preview truncated; all entered text will be sent]" else ""
            }
            val fingerprint=body.toString()
            if (lastShareBody!=fingerprint) { lastShareBody=fingerprint; lastShareId=java.util.UUID.randomUUID().toString() }
            body.put("shareId",lastShareId)
            AlertDialog.Builder(this).setTitle("Send to ${connection.getString("url")}").setMessage(preview)
                .setNegativeButton("Cancel",null).setPositiveButton("Send this item") { _, _ ->
                    Thread {
                        try {
                            val result=BrokerTransport.request(connection.getString("url"),"/api/native-share",body,connection.getString("token"))
                            state.status="Shared artifact ${result.getString("artifactId")} (${result.getLong("size")} bytes)"
                            runOnUiThread { selectedFile=null; shareText.setText(""); sharePreview.text="Transfer confirmed; selection cleared" }
                        } catch (_: Exception) { state.status="Sharing not confirmed. Item remains selected; no automatic retry." }
                    }.start()
                }.show()
        } catch (error: Exception) { state.status=error.message?.take(160) ?: "Cannot prepare share" }
    }
    private fun accessibilityEnabled(): Boolean =
        getSystemService(AccessibilityManager::class.java)
            .getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { it.resolveInfo.serviceInfo.packageName == packageName &&
                it.resolveInfo.serviceInfo.name == BridgeAccessibilityService::class.java.name }
    private fun notificationsEnabled(): Boolean =
        (Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
            getSystemService(NotificationManager::class.java).areNotificationsEnabled()
    override fun onResume() { super.onResume(); handler.post(refresh) }
    override fun onPause() { handler.removeCallbacks(refresh); super.onPause() }
}
