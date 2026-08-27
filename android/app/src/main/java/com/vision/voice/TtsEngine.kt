package com.vision.voice

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.Locale
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TtsEngine @Inject constructor(
    @ApplicationContext private val context: Context
) : TextToSpeech.OnInitListener {

    private var tts: TextToSpeech? = null
    private val _isSpeaking = MutableStateFlow(false)
    val isSpeaking: StateFlow<Boolean> = _isSpeaking

    // Streaming: queue sentences so VISION starts speaking while Ollama still generates
    private val sentenceQueue: Channel<String> = Channel(Channel.UNLIMITED)

    private var onInit: (() -> Unit)? = null
    private var initialized = false

    init {
        tts = TextToSpeech(context, this)
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            tts?.apply {
                language = Locale.US
                // Personalized VISION voice: calm, deep, clear — prefer male neural voice if available
                voices?.find { it.name.contains("male", true) && it.locale.language == "en" }?.let { voice = it }
                setSpeechRate(0.95f)
                setPitch(0.92f)
                setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(id: String?) { _isSpeaking.value = true }
                    override fun onDone(id: String?) { _isSpeaking.value = false }
                    override fun onError(id: String?) { _isSpeaking.value = false }
                })
            }
            initialized = true
            onInit?.invoke()
        }
    }

    fun speak(text: String, interrupt: Boolean = true) {
        if (!initialized) { onInit = { speak(text, interrupt) }; return }
        if (interrupt) tts?.stop()
        val id = UUID.randomUUID().toString()
        tts?.speak(text, if (interrupt) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD, null, id)
    }

    /** Streaming: split Ollama token stream into sentences and speak incrementally */
    fun speakStreaming(fullTextFlow: suspend () -> String) { /* wired in VisionAgent */ }

    fun speakSentence(sentence: String) = speak(sentence, interrupt = false)

    fun stop() {
        tts?.stop()
        _isSpeaking.value = false
    }

    fun shutdown() {
        tts?.shutdown()
    }

    companion object {
        // Split on sentence boundaries for low-latency playback
        fun splitIntoSentences(text: String): List<String> =
            text.split(Regex("(?<=[.!?])\\s+")).filter { it.isNotBlank() }
    }
}
