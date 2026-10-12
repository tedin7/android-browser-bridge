package net.arvos.browserbridge.companion

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.net.Uri
import android.provider.OpenableColumns
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.util.Base64
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import org.json.JSONObject

/** Owner console. Palette and hierarchy follow the Firefox extension options page. */
class MainActivity : Activity() {
    private object Palette {
        val background = Color.parseColor("#F4F7F4"); val ink = Color.parseColor("#173634"); val muted = Color.parseColor("#526A62")
        val accent = Color.parseColor("#136E5B"); val border = Color.parseColor("#D9E5DD"); val soft = Color.parseColor("#EAF3EC")
        val field = Color.parseColor("#FCFEFC"); val okBg = Color.parseColor("#E1EEE5"); val okInk = Color.parseColor("#25634B")
        val waitBg = Color.parseColor("#FFF0D6"); val waitInk = Color.parseColor("#876015")
        val errBg = Color.parseColor("#FBE5DF"); val errInk = Color.parseColor("#9C4032"); val idleBg = Color.parseColor("#E9EEEA"); val idleInk = Color.parseColor("#596B62")
    }
    private class App(val packageName: String, val label: String, val icon: Drawable?)

    private lateinit var state: ConnectionState
    private lateinit var badge: TextView
    private lateinit var status: TextView
    private lateinit var permissionStatus: TextView
    private lateinit var sessionStatus: TextView
    private lateinit var approvalCard: LinearLayout
    private lateinit var approvalDetails: TextView
    private lateinit var appList: LinearLayout
    private lateinit var appSummary: TextView
    private lateinit var sharePreview: TextView
    private lateinit var shareText: EditText
    private var apps: List<App> = emptyList()
    private var filter = ""
    private var selectedFile: ByteArray? = null
    private var selectedName = "shared-file"
    private var selectedMime = "application/octet-stream"
    private var lastShareBody: String? = null
    private var lastShareId: String? = null
    private val handler = Handler(Looper.getMainLooper())
    private val refresh = object : Runnable {
        override fun run() {
            val enabled = state.enabled
            val pending = state.approval
            when {
                pending != null -> setBadge("Approvazione richiesta", Palette.waitBg, Palette.waitInk)
                enabled -> setBadge("Controllo attivo", Palette.okBg, Palette.okInk)
                state.connection() == null -> setBadge("Non collegato", Palette.idleBg, Palette.idleInk)
                else -> setBadge("In pausa", Palette.idleBg, Palette.idleInk)
            }
            status.text = state.status
            sessionStatus.text = state.activeSession()?.let {
                "Sessione 10 minuti: ${label(it.target)} — ${(it.expiresAtElapsed - SystemClock.elapsedRealtime()).coerceAtLeast(0) / 1000}s rimanenti"
            } ?: "Nessuna sessione temporanea attiva"
            permissionStatus.text = (if (accessibilityEnabled()) "✓ Servizio Accessibilità attivo" else "✗ Servizio Accessibilità disattivato") +
                "\n" + (if (notificationsEnabled()) "✓ Notifiche STOP consentite" else "✗ " + (notificationProblem() ?: "Notifiche bloccate"))
            approvalCard.visibility = if (pending == null) View.GONE else View.VISIBLE
            pending?.let {
                val remaining = ((it.optLong("expiresAt") - System.currentTimeMillis()).coerceAtLeast(0) + 999) / 1000
                approvalDetails.text = "${it.optString("operation")} in ${label(it.optString("package"))} · scade tra ${remaining}s\n" +
                    (it.optJSONObject("args") ?: JSONObject()).toString().take(600)
            }
            handler.postDelayed(this, 1000)
        }
    }

    private fun dp(value: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics).toInt()
    private fun rounded(color: Int, radius: Int, stroke: Int? = null) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat(); stroke?.let { setStroke(dp(1), it) }
    }
    private fun LinearLayout.gap(value: Int) = addView(View(context), LinearLayout.LayoutParams(1, dp(value)))
    private fun text(parent: LinearLayout, value: String, size: Float = 14f, color: Int = Palette.ink, bold: Boolean = false, bottom: Int = 0) =
        TextView(this).also {
            it.text = value; it.textSize = size; it.setTextColor(color); it.setLineSpacing(0f, 1.2f)
            if (bold) it.typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            parent.addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(bottom) })
        }
    private enum class Kind { PRIMARY, SECONDARY, QUIET, DANGER }
    private fun button(parent: LinearLayout, value: String, kind: Kind = Kind.SECONDARY, weight: Boolean = false, action: () -> Unit) = Button(this).also {
        it.text = value; it.isAllCaps = false; it.textSize = 14f; it.stateListAnimator = null
        it.typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        it.minHeight = dp(46); it.setPadding(dp(14), dp(10), dp(14), dp(10))
        when (kind) {
            Kind.PRIMARY -> { it.background = rounded(Palette.accent, 10); it.setTextColor(Color.WHITE) }
            Kind.SECONDARY -> { it.background = rounded(Color.parseColor("#E6EEE7"), 10, Color.parseColor("#D4E1D6")); it.setTextColor(Color.parseColor("#2B634B")) }
            Kind.QUIET -> { it.background = rounded(Color.TRANSPARENT, 10); it.setTextColor(Palette.muted) }
            Kind.DANGER -> { it.background = rounded(Palette.errBg, 10); it.setTextColor(Palette.errInk) }
        }
        it.setOnClickListener { action() }
        val params = if (weight) LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = dp(8) }
            else LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) }
        parent.addView(it, params)
    }
    private fun row(parent: LinearLayout) = LinearLayout(this).also {
        it.orientation = LinearLayout.HORIZONTAL; it.gravity = Gravity.CENTER_VERTICAL
        parent.addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
    }
    private fun field(parent: LinearLayout, hint: String, multiline: Boolean = false) = EditText(this).also {
        it.hint = hint; it.textSize = 15f; it.setTextColor(Palette.ink); it.setHintTextColor(Color.parseColor("#82948A"))
        it.background = rounded(Palette.field, 10, Color.parseColor("#CBDCD0")); it.setPadding(dp(13), dp(11), dp(13), dp(11))
        if (!multiline) it.setSingleLine(true)
        parent.addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })
    }
    private fun card(parent: LinearLayout, mark: String, title: String, subtitle: String): LinearLayout {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; background = rounded(Color.WHITE, 20, Palette.border); setPadding(dp(20), dp(20), dp(20), dp(14))
            elevation = dp(1).toFloat()
        }
        parent.addView(card, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(16) })
        val heading = row(card)
        heading.addView(TextView(this).apply {
            text = mark; textSize = 18f; gravity = Gravity.CENTER; setTextColor(Palette.accent); background = rounded(Palette.soft, 11)
        }, LinearLayout.LayoutParams(dp(36), dp(36)).apply { marginEnd = dp(12) })
        val titles = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        heading.addView(titles, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        text(titles, title, 18f, Palette.ink, true)
        text(titles, subtitle, 13f, Palette.muted)
        card.gap(8)
        return card
    }
    private fun setBadge(value: String, background: Int, ink: Int) {
        badge.text = "● $value"; badge.setTextColor(ink); badge.background = rounded(background, 100)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        state = ConnectionState(this)
        window.statusBarColor = Palette.background
        if (Build.VERSION.SDK_INT >= 23) window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(18), dp(22), dp(18), dp(28)) }

        // Header, as in the extension: brand mark, name, state badge.
        val top = row(column)
        top.addView(TextView(this).apply {
            text = "BB"; textSize = 15f; gravity = Gravity.CENTER; setTextColor(Color.parseColor("#F7FFFA"))
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD); background = rounded(Color.parseColor("#176D58"), 12)
        }, LinearLayout.LayoutParams(dp(40), dp(40)).apply { marginEnd = dp(11) })
        top.addView(TextView(this).apply { text = "Browser Bridge"; textSize = 19f; setTextColor(Color.parseColor("#183D34")); typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD) },
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        badge = TextView(this).apply { textSize = 12f; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD); setPadding(dp(11), dp(6), dp(11), dp(6)) }
        top.addView(badge)
        column.gap(22)
        text(column, "COMPANION ANDROID · SPERIMENTALE", 11f, Color.parseColor("#5B7C6B"), true, 8)
        text(column, "Le tue app. Sotto il tuo controllo.", 28f, Palette.ink, true, 10)
        text(column, "Il server collegato può leggere e usare solo le app che scegli qui. Per le pagine web resta preferibile l'estensione Firefox; il companion serve per l'interfaccia delle app.", 15f, Color.parseColor("#526C61"), bottom = 22)

        // Pending approval: shown only while a request waits.
        approvalCard = card(column, "!", "Azione da approvare", "Decidi tu: una volta, per 10 minuti o per sempre.")
        approvalCard.background = rounded(Color.parseColor("#FFFBF2"), 20, Color.parseColor("#EBDDBC"))
        approvalDetails = text(approvalCard, "", 13f, Palette.ink, bottom = 10)
        val decisions = row(approvalCard)
        button(decisions, "Una volta", Kind.PRIMARY, weight = true) { state.approval?.let { state.decideApproval(it.getString("id"), true); finish() } }
        button(decisions, "10 minuti", Kind.SECONDARY, weight = true) { state.approval?.let { state.decideApproval(it.getString("id"), true, forSession = true); returnToApp(it) } }
        button(approvalCard, "Approva sempre questa app", Kind.SECONDARY) {
            state.approval?.let {
                val target = it.optString("package")
                AlertDialog.Builder(this).setTitle("Approvazione permanente")
                    .setMessage("${label(target)} non chiederà più conferma per click, compilazione, scorrimento e indietro. Puoi revocarla in qualsiasi momento dall'elenco App. STOP ferma comunque tutto.")
                    .setNegativeButton("Annulla", null).setPositiveButton("Approva sempre") { _, _ ->
                        state.decideApproval(it.getString("id"), true, forever = true); renderApps(); returnToApp(it)
                    }.show()
            }
        }
        button(approvalCard, "Nega", Kind.DANGER) { state.approval?.let { state.decideApproval(it.getString("id"), false) } }
        approvalCard.visibility = View.GONE

        // Control and status.
        val control = card(column, "⏻", "Controllo remoto", "Attivalo quando vuoi che il server agisca sulle tue app.")
        status = text(control, state.status, 14f, Palette.ink, bottom = 6)
        permissionStatus = text(control, "", 13f, Palette.muted, bottom = 4)
        sessionStatus = text(control, "", 13f, Palette.muted, bottom = 12)
        val consent = CheckBox(this).apply {
            text = "Autorizzo questo server a leggere e controllare le app consentite mentre il controllo è attivo"
            textSize = 13f; setTextColor(Color.parseColor("#2D5943")); isChecked = state.enabled
            background = rounded(Color.parseColor("#F2F7F2"), 12, Color.parseColor("#D9E7DC")); setPadding(dp(10), dp(12), dp(12), dp(12))
            if (Build.VERSION.SDK_INT >= 21) buttonTintList = android.content.res.ColorStateList.valueOf(Palette.accent)
        }
        control.addView(consent, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(12) })
        consent.setOnCheckedChangeListener { _, checked ->
            if (!checked) {
                state.enabled = false; state.approval = null
                ControlNotifications.cancel(getSystemService(NotificationManager::class.java))
            }
            state.status = Policy.consentStatus(checked, state.status)
        }
        button(control, "Attiva controllo remoto", Kind.PRIMARY) {
            try {
                require(consent.isChecked) { "Seleziona prima l'autorizzazione" }
                require(state.allowed.isNotEmpty()) { "Consenti almeno un'app nell'elenco App" }
                require(state.connection() != null) { "Collega prima un server" }
                require(accessibilityEnabled()) { "Attiva Browser Bridge Companion nelle impostazioni Accessibilità, poi torna qui" }
                require(notificationsEnabled()) { notificationProblem() ?: "Consenti le notifiche per mantenere visibile STOP" }
                state.enabled = true; state.status = "Attivato; in attesa del servizio Accessibilità"
            } catch (error: Exception) { state.status = error.message?.take(160) ?: "Impossibile attivare" }
        }
        val permissions = row(control)
        button(permissions, "Accessibilità", Kind.SECONDARY, weight = true) { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        button(permissions, "Notifiche", Kind.SECONDARY, weight = true) {
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
            else startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
        }
        val stops = row(control)
        button(stops, "STOP", Kind.DANGER, weight = true) {
            state.enabled = false; state.approval = null; state.status = "Fermato localmente"; consent.isChecked = false
            ControlNotifications.cancel(getSystemService(NotificationManager::class.java))
        }
        button(stops, "Revoca sessione", Kind.QUIET, weight = true) { state.clearSession(); state.status = "Sessione temporanea revocata" }

        // App allowlist with permanent approval per app.
        val appsCard = card(column, "▦", "App", "Consenti le app da controllare. «Sempre» salta la richiesta di approvazione.")
        appSummary = text(appsCard, "", 13f, Palette.muted, bottom = 8)
        val search = field(appsCard, "Cerca un'app")
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) { filter = s?.toString()?.trim() ?: ""; renderApps() }
        })
        appList = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        appsCard.addView(appList)
        text(appList, "Caricamento app…", 13f, Palette.muted)
        val manual = field(appsCard, "Altro pacchetto (es. com.example.app)")
        button(appsCard, "Aggiungi pacchetto", Kind.QUIET) {
            try {
                val added = Policy.packages(manual.text.toString())
                require(added.isNotEmpty() && packageName !in added) { "Inserisci un nome di pacchetto valido" }
                state.allowed = state.allowed + added; manual.setText(""); renderApps()
            } catch (error: Exception) { state.status = error.message?.take(160) ?: "Pacchetto non valido" }
        }

        // Pairing.
        val pairCard = card(column, "+", "Collega un server", "Il codice BB1 arriva dal tuo assistente o terminale.")
        val pairing = field(pairCard, "Incolla la stringa BB1 per un NUOVO dispositivo nativo", multiline = true)
        button(pairCard, "Collega server", Kind.PRIMARY) {
            try {
                require(consent.isChecked) { "Seleziona prima l'autorizzazione" }
                require(state.allowed.isNotEmpty()) { "Consenti almeno un'app nell'elenco App" }
                val encoded = pairing.text.toString().trim()
                require(encoded.startsWith("BB1.") && encoded.length <= 8192) { "Incolla una stringa BB1 valida" }
                val data = JSONObject(String(Base64.decode(encoded.substring(4), Base64.URL_SAFE or Base64.NO_WRAP), Charsets.UTF_8))
                val origin = Policy.origin(data.getString("url")); val code = data.getString("code")
                require(code.length in 1..128) { "Codice di collegamento non valido" }
                state.enabled = false; state.status = "Collegamento…"
                Thread {
                    try {
                        // Pairing is one-use: never automatically retry a lost response.
                        val result = BrokerTransport.request(origin, "/api/pair", JSONObject().put("code", code))
                        result.put("url", origin)
                        require(result.getString("token").isNotBlank() && result.getString("device").isNotBlank())
                        state.saveConnection(result); state.status = "Collegato. Attiva Accessibilità, poi il controllo remoto."
                        runOnUiThread { pairing.setText("") }
                    } catch (_: Exception) { state.status = "Collegamento non confermato. Crea un nuovo codice prima di riprovare." }
                }.start()
            } catch (error: Exception) { state.status = error.message?.take(160) ?: "Impostazioni di collegamento non valide" }
        }

        // Explicit share.
        val shareCard = card(column, "↗", "Condividi con il server", "Indipendente dal controllo: nulla parte senza la tua conferma.")
        shareText = field(shareCard, "Testo o URL da condividere", multiline = true)
        sharePreview = text(shareCard, "Nessun file selezionato.", 13f, Palette.muted, bottom = 8)
        val shareButtons = row(shareCard)
        button(shareButtons, "Scegli file (1 MiB)", Kind.SECONDARY, weight = true) {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"), 20)
        }
        button(shareButtons, "Rimuovi file", Kind.QUIET, weight = true) { selectedFile = null; sharePreview.text = "Nessun file selezionato" }
        button(shareCard, "Rivedi e invia", Kind.PRIMARY) { reviewShare() }
        text(column, "Le password non vengono mai lette. STOP nella notifica ferma subito il controllo.", 11f, Color.parseColor("#779080"))

        if (intent.action == Intent.ACTION_SEND) {
            intent.getStringExtra(Intent.EXTRA_TEXT)?.let { shareText.setText(it.take(65536)) }
            @Suppress("DEPRECATION")
            val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
            if (uri != null) loadFile(uri)
        }
        setContentView(ScrollView(this).apply {
            setBackgroundColor(Palette.background)
            addView(column, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        })
        loadApps()
    }

    private fun label(target: String): String = apps.firstOrNull { it.packageName == target }?.label ?: try {
        packageManager.getApplicationLabel(packageManager.getApplicationInfo(target, 0)).toString()
    } catch (_: Exception) { target }
    private fun loadApps() {
        Thread {
            val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            val found = packageManager.queryIntentActivities(launcher, 0)
                .filter { it.activityInfo.packageName != packageName }
                .distinctBy { it.activityInfo.packageName }
                .map { App(it.activityInfo.packageName, it.loadLabel(packageManager).toString(), try { it.loadIcon(packageManager) } catch (_: Exception) { null }) }
                .sortedBy { it.label.lowercase() }
            runOnUiThread { apps = found; renderApps() }
        }.start()
    }
    private fun renderApps() {
        val allowed = state.allowed; val always = state.always
        appSummary.text = "${allowed.size} consentite · ${always.size} con approvazione permanente"
        appList.removeAllViews()
        // Allowed packages without a launcher entry stay visible so they can be removed.
        val extra = allowed.filter { name -> apps.none { it.packageName == name } }.map { App(it, it, null) }
        val shown = (extra + apps).filter { filter.isEmpty() || it.label.contains(filter, true) || it.packageName.contains(filter, true) }
            .sortedWith(compareByDescending<App> { it.packageName in allowed }.thenBy { it.label.lowercase() })
        if (shown.isEmpty()) text(appList, "Nessuna app trovata", 13f, Palette.muted)
        for (app in shown.take(if (filter.isEmpty()) 60 else 200)) {
            val item = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(10), dp(8), dp(6), dp(8))
                background = rounded(if (app.packageName in allowed) Color.parseColor("#F2F7F2") else Color.WHITE, 14, Color.parseColor("#EDF2EC"))
            }
            appList.addView(item, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(6) })
            item.addView(ImageView(this).apply { app.icon?.let { setImageDrawable(it) } }, LinearLayout.LayoutParams(dp(34), dp(34)).apply { marginEnd = dp(10) })
            val names = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            item.addView(names, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            text(names, app.label, 14f, Palette.ink, true)
            text(names, app.packageName, 11f, Color.parseColor("#67806F"))
            val toggles = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.END }
            item.addView(toggles)
            val allow = Switch(this).apply { text = "Consenti"; textSize = 12f; setTextColor(Palette.muted); isChecked = app.packageName in allowed }
            val forever = Switch(this).apply { text = "Sempre"; textSize = 12f; setTextColor(Palette.muted); isChecked = app.packageName in always; isEnabled = app.packageName in allowed }
            toggles.addView(allow); toggles.addView(forever)
            allow.setOnCheckedChangeListener { _, checked ->
                state.allowed = if (checked) state.allowed + app.packageName else state.allowed - app.packageName
                if (state.allowed.isEmpty() && state.enabled) { state.enabled = false; state.status = "Nessuna app consentita: controllo fermato" }
                renderApps()
            }
            forever.setOnCheckedChangeListener { view, checked ->
                if (!checked) { state.always = state.always - app.packageName; renderApps(); return@setOnCheckedChangeListener }
                AlertDialog.Builder(this).setTitle("Approvazione permanente")
                    .setMessage("${app.label} non chiederà più conferma per click, compilazione, scorrimento e indietro. STOP ferma comunque tutto; puoi revocarla qui.")
                    .setNegativeButton("Annulla") { _, _ -> view.isChecked = false }
                    .setOnCancelListener { view.isChecked = false }
                    .setPositiveButton("Approva sempre") { _, _ -> state.always = state.always + app.packageName; renderApps() }.show()
            }
        }
        if (filter.isEmpty() && shown.size > 60) text(appList, "Altre ${shown.size - 60} app: usa la ricerca", 12f, Palette.muted)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 20 && resultCode == RESULT_OK) data?.data?.let { loadFile(it) }
    }
    private fun loadFile(uri: Uri) {
        if (uri.scheme != "content") { state.status = "Scegli il file dal selettore documenti di Android"; return }
        Thread {
            try {
                val name = contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) cursor.getString(0).take(128) else "shared-file"
                } ?: "shared-file"
                val mime = contentResolver.getType(uri) ?: "application/octet-stream"
                val bytes = contentResolver.openInputStream(uri)?.use { input ->
                    val output = java.io.ByteArrayOutputStream(); val buffer = ByteArray(8192)
                    while (output.size() <= 1048576) {
                        val count = input.read(buffer, 0, minOf(buffer.size, 1048577 - output.size()))
                        if (count < 0) break
                        output.write(buffer, 0, count)
                    }
                    output.toByteArray()
                } ?: throw IllegalArgumentException("Cannot open file")
                require(bytes.size <= 1048576) { "File exceeds 1 MiB" }
                runOnUiThread { selectedFile = bytes; selectedName = name; selectedMime = mime; sharePreview.text = "Pronto: $name ($mime, ${bytes.size} byte). Non inviato." }
            } catch (_: Exception) { state.status = "File non disponibile o oltre 1 MiB; nulla inviato" }
        }.start()
    }
    private fun reviewShare() {
        try {
            val connection = state.connection() ?: throw IllegalArgumentException("Collega prima un server")
            val body = JSONObject().put("device", connection.getString("device"))
            val file = selectedFile
            val preview = if (file != null) {
                body.put("mimeType", selectedMime).put("name", selectedName).put("dataBase64", Base64.encodeToString(file, Base64.NO_WRAP))
                "$selectedName ($selectedMime, ${file.size} byte)"
            } else {
                val value = shareText.text.toString()
                require(value.isNotEmpty() && value.toByteArray(Charsets.UTF_8).size <= 65536) { "Inserisci testo o URL fino a 64 KiB" }
                body.put("mimeType", "text/plain").put("name", "shared-text.txt").put("text", value)
                value.take(1000) + if (value.length > 1000) "\n[Anteprima troncata; verrà inviato tutto il testo]" else ""
            }
            val fingerprint = body.toString()
            if (lastShareBody != fingerprint) { lastShareBody = fingerprint; lastShareId = java.util.UUID.randomUUID().toString() }
            body.put("shareId", lastShareId)
            AlertDialog.Builder(this).setTitle("Invia a ${connection.getString("url")}").setMessage(preview)
                .setNegativeButton("Annulla", null).setPositiveButton("Invia") { _, _ ->
                    Thread {
                        try {
                            val result = BrokerTransport.request(connection.getString("url"), "/api/native-share", body, connection.getString("token"))
                            state.status = "Condiviso ${result.getString("artifactId")} (${result.getLong("size")} byte)"
                            runOnUiThread { selectedFile = null; shareText.setText(""); sharePreview.text = "Invio confermato; selezione rimossa" }
                        } catch (_: Exception) { state.status = "Invio non confermato. L'elemento resta selezionato; nessun nuovo tentativo automatico." }
                    }.start()
                }.show()
        } catch (error: Exception) { state.status = error.message?.take(160) ?: "Impossibile preparare l'invio" }
    }
    private fun returnToApp(pending: JSONObject) {
        val target = pending.optString("package")
        if (target == packageName || target !in state.allowed) return
        try {
            // Only this explicit local approval gesture resumes the app that requested it.
            val launch = packageManager.getLaunchIntentForPackage(target)
            if (launch != null) startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED))
            finish()
        } catch (_: Exception) { state.status = "Approvato. Torna a ${label(target)}." }
    }
    // Some vendor builds (e.g. ColorOS) omit a running service from the manager list, so accept
    // any of: the service bound in this process, the secure setting, or the manager list.
    private fun accessibilityEnabled(): Boolean {
        if (BridgeAccessibilityService.connected.get()) return true
        val component = android.content.ComponentName(this, BridgeAccessibilityService::class.java)
        val setting = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: ""
        if (setting.split(':').any { android.content.ComponentName.unflattenFromString(it) == component }) return true
        return getSystemService(AccessibilityManager::class.java)
            .getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { it.resolveInfo.serviceInfo.packageName == packageName &&
                it.resolveInfo.serviceInfo.name == BridgeAccessibilityService::class.java.name }
    }
    private fun notificationProblem(): String? = ControlNotifications.blockedReason(getSystemService(NotificationManager::class.java))
    private fun notificationsEnabled(): Boolean =
        (Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
            notificationProblem() == null
    override fun onResume() { super.onResume(); handler.post(refresh); if (::appList.isInitialized && apps.isNotEmpty()) renderApps() }
    override fun onPause() { handler.removeCallbacks(refresh); super.onPause() }
}
