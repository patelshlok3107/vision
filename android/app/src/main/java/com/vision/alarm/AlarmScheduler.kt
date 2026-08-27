package com.vision.alarm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AlarmScheduler @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

    /** Never overwrites — each alarm gets its own PendingIntent requestCode = alarmId */
    fun schedule(entity: AlarmEntity) {
        val intent = Intent(context, AlarmReceiver::class.java).apply {
            putExtra("alarm_id", entity.id)
            putExtra("title", entity.title)
            putExtra("speakText", entity.speakText)
            putExtra("type", entity.type)
            putExtra("repeatIntervalMinutes", entity.repeatIntervalMinutes ?: -1)
        }
        val pi = PendingIntent.getBroadcast(
            context, entity.id.toInt(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        // Real OS alarm — survives app kill, doze via setExactAndAllowWhileIdle
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !am.canScheduleExactAlarms()) {
            // fallback to inexact if permission not granted — prompt user in UI
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, entity.triggerAtMillis, pi)
        } else {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, entity.triggerAtMillis, pi)
        }
    }

    fun cancel(alarmId: Long) {
        val pi = PendingIntent.getBroadcast(
            context, alarmId.toInt(), Intent(context, AlarmReceiver::class.java),
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
        ) ?: return
        am.cancel(pi)
        pi.cancel()
    }

    fun scheduleRepeating(entity: AlarmEntity) {
        // For "every 2 hours" — schedule next occurrence only, receiver reschedules
        schedule(entity)
    }
}
