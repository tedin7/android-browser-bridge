package net.arvos.browserbridge.companion

import android.app.NotificationChannel
import android.app.NotificationManager

object ControlNotifications {
    const val CONTROL = "control"
    const val APPROVAL = "action-approval-v1"
    fun prepare(manager: NotificationManager) {
        manager.createNotificationChannel(NotificationChannel(CONTROL, "Controllo remoto (STOP)", NotificationManager.IMPORTANCE_LOW))
        manager.createNotificationChannel(NotificationChannel(APPROVAL, "Approvazione azioni", NotificationManager.IMPORTANCE_HIGH))
    }
    fun blockedReason(manager: NotificationManager): String? {
        prepare(manager)
        return when {
            !manager.areNotificationsEnabled() -> "Allow this app's notifications in Android settings so STOP and approvals are visible"
            manager.getNotificationChannel(CONTROL)?.importance == NotificationManager.IMPORTANCE_NONE -> "Enable the Controllo remoto (STOP) notification channel in Android app notification settings"
            manager.getNotificationChannel(APPROVAL)?.importance == NotificationManager.IMPORTANCE_NONE -> "Enable the Approvazione azioni notification channel in Android app notification settings"
            else -> null
        }
    }
    fun cancel(manager: NotificationManager) { manager.cancel(1); manager.cancel(2) }
}
