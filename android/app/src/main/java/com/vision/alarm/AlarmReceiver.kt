package com.vision.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class AlarmReceiver : BroadcastReceiver() {
    @Inject lateinit var repository: AlarmRepository

    override fun onReceive(context: Context, intent: Intent) {
        val title = intent.getStringExtra("title") ?: "VISION Alarm"
        val speakText = intent.getStringExtra("speakText") ?: title
        val type = intent.getStringExtra("type") ?: "ALARM"
        val repeatMins = intent.getIntExtra("repeatIntervalMinutes", -1).takeIf { it != -1 }
        val alarmId = intent.getLongExtra("alarm_id", -1)

        // Start foreground service that shows notification + speaks
        val svc = Intent(context, AlarmService::class.java).apply {
            putExtra("title", title)
            putExtra("speakText", speakText)
            putExtra("type", type)
            putExtra("alarm_id", alarmId)
        }
        ContextCompat.startForegroundService(context, svc)

        // Reschedule repeating
        if (repeatMins != null && alarmId != -1L) {
            CoroutineScope(Dispatchers.IO).launch {
                repository.rescheduleRepeating(alarmId, repeatMins)
            }
        }
    }
}
