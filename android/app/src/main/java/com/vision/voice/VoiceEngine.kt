package com.vision.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class VoiceEngine @Inject constructor(
    @ApplicationContext private val context: Context,
    private val tts: TtsEngine
) {
    private var recognizer: SpeechRecognizer? = null

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state

    private val _transcript = Channel<String>(Channel.UNLIMITED)
    val transcript: Flow<String> = _transcript.receiveAsFlow()

    sealed class State { object Idle : State(); object Listening : State(); object Processing : State(); data class Speaking(val text: String) : State() }

    fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            _state.value = State.Idle
            return
        }
        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(p: Bundle?) { _state.value = State.Listening }
                override fun onBeginningOfSpeech() { _state.value = State.Listening }
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(b: ByteArray?) {}
                override fun onEndOfSpeech() { _state.value = State.Processing }
                override fun onError(error: Int) { _state.value = State.Idle }
                override fun onResults(results: Bundle?) {
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val text = matches?.firstOrNull() ?: ""
                    if (text.isNotBlank()) _transcript.trySend(text)
                    _state.value = State.Idle
                }
                override fun onPartialResults(p: Bundle?) {
                    val matches = p?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    matches?.firstOrNull()?.let { /* partial UI */ }
                }
                override fun onEvent(type: Int, params: Bundle?) {}
            })
        }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        }
        recognizer?.startListening(intent)
    }

    fun stopListening() {
        recognizer?.stopListening()
        _state.value = State.Idle
    }

    fun speak(text: String, interrupt: Boolean = true) {
        _state.value = State.Speaking(text)
        tts.speak(text, interrupt)
    }

    fun stopSpeaking() {
        tts.stop()
        _state.value = State.Idle
    }

    fun destroy() { recognizer?.destroy(); recognizer = null }
}
