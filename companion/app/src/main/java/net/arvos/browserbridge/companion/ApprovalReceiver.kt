package net.arvos.browserbridge.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class ApprovalReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val id = intent?.getStringExtra("id") ?: return
        ConnectionState(context).decideApproval(id, intent.getBooleanExtra("approve", false), intent.getBooleanExtra("session", false), intent.getBooleanExtra("always", false))
    }
}
