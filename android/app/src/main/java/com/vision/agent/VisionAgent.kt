package com.vision.agent

import com.vision.alarm.AlarmEntity
import com.vision.alarm.AlarmRepository
import com.vision.data.TokenManager
import com.vision.data.remote.AgentChatRequest
import com.vision.data.remote.ApiService
import com.vision.voice.LocalIntentParser
import com.vision.voice.TtsEngine
import kotlinx.coroutines.flow.first
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Two-brain orchestrator:
 * 1. Try local parser (instant, offline)
 * 2. Fallback to Ollama via Django ai_agent POST /api/ai/chat/ (StreamingHttpResponse NDJSON)
 * 3. If Ollama down -> still execute via local + speak fallback
 */
@Singleton
class VisionAgent @Inject constructor(
    private val api: ApiService,
    private val tokens: TokenManager,
    private val alarms: AlarmRepository,
    private val tts: TtsEngine
) {
    sealed class Result(val speak: String) {
        class Handled(speak: String) : Result(speak)
        class Error(speak: String) : Result(speak)
    }

    suspend fun handleVoice(raw: String): Result {
        val intent = LocalIntentParser.parse(raw)
        when (intent) {
            is LocalIntentParser.Intent.SetAlarm -> {
                val cal = LocalIntentParser.scheduledTimeForAlarm(intent.time)
                alarms.add(AlarmEntity(title = intent.label, speakText = intent.speakText, triggerAtMillis = cal.timeInMillis, type = "ALARM"))
                return Result.Handled("Done, Shlok. Alarm set for ${intent.time}.")
            }
            is LocalIntentParser.Intent.SetReminder -> {
                val whenMs = System.currentTimeMillis() + intent.delayMinutes * 60_000L
                val speak = "Shlok, it's time to ${intent.title.lowercase()}."
                alarms.add(AlarmEntity(title = intent.title, speakText = speak, triggerAtMillis = whenMs, type = "REMINDER", repeatIntervalMinutes = intent.repeatMinutes))
                val human = if (intent.delayMinutes >= 60) "${intent.delayMinutes/60} hour(s)" else "${intent.delayMinutes} minutes"
                return Result.Handled("Done. I'll remind you to ${intent.title} in $human.")
            }
            is LocalIntentParser.Intent.SetRepeatingReminder -> {
                val whenMs = System.currentTimeMillis() + intent.intervalMinutes * 60_000L
                alarms.add(AlarmEntity(title = intent.title, speakText = "Shlok, it's time to ${intent.title.lowercase()}.", triggerAtMillis = whenMs, type = "REMINDER", repeatIntervalMinutes = intent.intervalMinutes))
                return Result.Handled("Done. I'll remind you to ${intent.title} every ${intent.intervalMinutes/60} hours.")
            }
            is LocalIntentParser.Intent.MorningBriefing -> { /* fall through to LLM for rich briefing */ }
            is LocalIntentParser.Intent.Unknown -> { /* fall through */ }
            else -> {}
        }

        return try {
            val token = tokens.tokenFlow.first() ?: return Result.Error("You're not logged in. Please login first.")
            val body = api.agentChatStream(tokens.authHeader(token), AgentChatRequest(message = raw))
            // NDJSON streaming: each line is JSON {type: token|tool|done, content: ...}
            val fullText = StringBuilder()
            body.byteStream().bufferedReader().forEachLine { line ->
                if (line.isBlank()) return@forEachLine
                try {
                    val obj = JSONObject(line)
                    when (obj.optString("type")) {
                        "token" -> {
                            val chunk = obj.optString("content")
                            fullText.append(chunk)
                            // streaming TTS: speak sentence-by-sentence
                            if (chunk.contains(".") || chunk.contains("?") || chunk.contains("!")) {
                                val sentences = TtsEngine.splitIntoSentences(fullText.toString())
                                sentences.lastOrNull()?.let { /* buffered */ }
                            }
                        }
                        "tool" -> {
                            val name = obj.optString("tool")
                            val args = obj.optJSONObject("args")
                            if (name == "create_reminder") {
                                val title = args?.optString("title") ?: return@forEachLine
                                val delay = args.optInt("delay_minutes", 10)
                                alarms.add(AlarmEntity(title = title, speakText = "Shlok, $title", triggerAtMillis = System.currentTimeMillis() + delay*60_000L, type = "REMINDER"))
                            }
                        }
                        else -> fullText.append(obj.optString("content"))
                    }
                } catch (_: Exception) { fullText.append(line) }
            }
            val reply = fullText.toString().ifBlank { "Done, Shlok." }
            TtsEngine.splitIntoSentences(reply).forEach { tts.speakSentence(it) }
            Result.Handled(reply)
        } catch (e: Exception) {
            Result.Error("VISION is offline, but your alarms still work. ${e.message ?: "Try 'remind me in 10 minutes'."}")
        }
    }
}
