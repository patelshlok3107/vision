package com.vision.voice

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.vision.MainActivity
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class VisionVoiceService : Service() {
    @Inject lateinit var voiceEngine: VoiceEngine
    @Inject lateinit var tts: TtsEngine

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(3, foregroundNotification())
        when (intent?.action) {
            "ACTION_LISTEN" -> voiceEngine.startListening()
            "ACTION_STOP" -> { voiceEngine.stopListening(); voiceEngine.stopSpeaking() }
            "ACTION_SPEAK" -> voiceEngine.speak(intent.getStringExtra("text") ?: "")
        }
        return START_NOT_STICKY
    }

    private fun foregroundNotification(): Notification {
        val pi = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, "vision_voice")
            .setContentTitle("VISION listening")
            .setContentText("Tap to talk to VISION")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }
}
