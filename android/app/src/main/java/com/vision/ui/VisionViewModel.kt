package com.vision.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vision.agent.VisionAgent
import com.vision.alarm.AlarmRepository
import com.vision.data.remote.ApiService
import com.vision.data.TokenManager
import com.vision.voice.TtsEngine
import com.vision.voice.VoiceEngine
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class VisionViewModel @Inject constructor(
    private val agent: VisionAgent,
    private val voice: VoiceEngine,
    private val tts: TtsEngine,
    private val alarms: AlarmRepository,
    private val api: ApiService,
    private val tokens: TokenManager
) : ViewModel() {

    val alarmsFlow = alarms.alarms.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val voiceState = voice.state
    val isSpeaking = tts.isSpeaking

    private val _lastReply = MutableStateFlow("Good evening, Shlok.")
    val lastReply: StateFlow<String> = _lastReply

    private val _briefing = MutableStateFlow<String?>(null)
    val briefing: StateFlow<String?> = _briefing

    init {
        viewModelScope.launch { voice.transcript.collect { text -> onVoiceInput(text) } }
    }

    fun onMicTap() {
        if (isSpeaking.value) { tts.stop(); return } // voice interruption
        voice.startListening()
    }

    fun onVoiceInput(text: String) {
        viewModelScope.launch {
            val res = agent.handleVoice(text)
            _lastReply.value = res.speak
            tts.speak(res.speak)
        }
    }

    fun onTextSubmit(text: String) = onVoiceInput(text)

    fun stopSpeaking() = tts.stop()

    fun loadBriefing() {
        viewModelScope.launch {
            try {
                val tok = tokens.tokenFlow.first() ?: return@launch
                val b = api.morningBriefing(tokens.authHeader(tok))
                _briefing.value = b.text
            } catch (_: Exception) {}
        }
    }
}
