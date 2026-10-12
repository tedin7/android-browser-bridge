package net.arvos.browserbridge.companion

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class StopReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        ConnectionState(context).apply { enabled = false; approval = null; status = "Stopped locally" }
        ControlNotifications.cancel(context.getSystemService(NotificationManager::class.java))
    }
}
