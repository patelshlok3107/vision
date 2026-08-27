package com.vision.alarm

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.vision.MainActivity
import com.vision.voice.TtsEngine
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.*

@AndroidEntryPoint
class AlarmService : Service() {
    @Inject lateinit var tts: TtsEngine

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val title = intent?.getStringExtra("title") ?: "VISION"
        val speakText = intent?.getStringExtra("speakText") ?: title
        val type = intent?.getStringExtra("type") ?: "ALARM"

        startForeground(1, buildNotification(title, type))

        // Personalized voice — speaks the alarm
        scope.launch {
            // small delay so notification is visible first
            delay(400)
            tts.speak(speakText, interrupt = true)
        }

        // Auto-stop foreground after 30s (user can snooze/dismiss in UI)
        scope.launch {
            delay(30_000)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    private fun buildNotification(title: String, type: String): Notification {
        val pi = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val channel = if (type == "ALARM") "vision_alarms" else "vision_reminders"
        return NotificationCompat.Builder(this, channel)
            .setContentTitle(if (type == "ALARM") "VISION Alarm" else "VISION Reminder")
            .setContentText(title)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setContentIntent(pi)
            .setAutoCancel(true)
            .addAction(NotificationCompat.Action(0, "Snooze 10m", snoozeIntent(10)))
            .addAction(NotificationCompat.Action(0, "Dismiss", dismissIntent()))
            .build()
    }

    private fun snoozeIntent(mins: Int): PendingIntent {
        val i = Intent(this, AlarmReceiver::class.java).apply {
            putExtra("title", "Snoozed")
            putExtra("speakText", "Shlok, your snoozed reminder is back.")
            putExtra("type", "REMINDER")
        }
        return PendingIntent.getBroadcast(this, (System.currentTimeMillis() % Int.MAX_VALUE).toInt(), i, PendingIntent.FLAG_IMMUTABLE)
    }
    private fun dismissIntent(): PendingIntent =
        PendingIntent.getService(this, 99, Intent(this, AlarmService::class.java).apply { action = "DISMISS" }, PendingIntent.FLAG_IMMUTABLE)

    override fun onDestroy() { scope.cancel(); super.onDestroy() }
}
