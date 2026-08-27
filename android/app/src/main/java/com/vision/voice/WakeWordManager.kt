package com.vision.voice

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * V2: replace stub with Porcupine / OpenWakeWord.
 * V1: uses tap-to-talk + optional always-listening via SpeechRecognizer.
 * Never streams mic to Ollama — wake word is entirely on-device.
 */
@Singleton
class WakeWordManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val voiceEngine: VoiceEngine
) {
    private val _isWakeWordEnabled = MutableStateFlow(false)
    val isWakeWordEnabled: StateFlow<Boolean> = _isWakeWordEnabled

    private val _isDetected = MutableStateFlow(false)
    val isDetected: StateFlow<Boolean> = _isDetected

    fun enable() {
        _isWakeWordEnabled.value = true
        // TODO V2: init Picovoice Porcupine with keyword "VISION" / "Hey VISION"
        // PorcupineManager.fromKeyword(context, Porcupine.BuiltInKeyword.PICOVOICE) { onWakeWord() }
    }

    fun disable() {
        _isWakeWordEnabled.value = false
    }

    private fun onWakeWord() {
        _isDetected.value = true
        voiceEngine.startListening()
        // haptic + "Yes, Shlok?" is spoken by caller
    }

    fun reset() { _isDetected.value = false }
}
