package com.vision

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class VisionApp : Application() {
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val nm = getSystemService(NotificationManager::class.java)
        listOf(
            NotificationChannel("vision_alarms", "VISION Alarms", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Time-critical alarms spoken by VISION"
                enableVibration(true)
                setBypassDnd(true)
            },
            NotificationChannel("vision_reminders", "VISION Reminders", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Reminders and briefings"
            },
            NotificationChannel("vision_voice", "VISION Voice", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Voice service foreground notification"
                setShowBadge(false)
            }
        ).forEach { nm.createNotificationChannel(it) }
    }
}
