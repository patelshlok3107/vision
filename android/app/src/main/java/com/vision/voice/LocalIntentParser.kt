package com.vision.voice

import java.time.LocalDateTime
import java.time.LocalTime
import java.time.temporal.ChronoUnit
import java.util.Calendar

/**
 * Local brain — no Ollama needed. Handles deterministic commands instantly.
 * This is the Emergency Fallback: works offline.
 */
object LocalIntentParser {

    sealed class Intent {
        data class SetAlarm(val time: LocalTime, val label: String, val speakText: String) : Intent()
        data class SetReminder(val delayMinutes: Int, val title: String, val repeatMinutes: Int? = null) : Intent()
        data class SetRepeatingReminder(val title: String, val intervalMinutes: Int) : Intent()
        data class CancelAlarm(val labelContains: String) : Intent()
        data object MorningBriefing : Intent()
        data object ListTasks : Intent()
        data class OpenApp(val packageHint: String) : Intent()
        data class Unknown(val raw: String) : Intent()
    }

    fun parse(raw: String): Intent {
        val t = raw.lowercase().trim()
            .removePrefix("hey vision").removePrefix("vision").removePrefix(",").trim()

        // "wake me up at 7 am / 7:30 tomorrow morning"
        Regex("""(wake me up|set.*alarm).*?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?""").find(t)?.let { m ->
            val h = m.groupValues[2].toInt()
            val min = m.groupValues[3].toIntOrNull() ?: 0
            val ampm = m.groupValues[4]
            val hour24 = when (ampm) {
                "pm" -> if (h == 12) 12 else h + 12
                "am" -> if (h == 12) 0 else h
                else -> h
            }
            return Intent.SetAlarm(LocalTime.of(hour24, min), label = "Wake up", speakText = "Good morning, Shlok. It's ${h}:${min.toString().padStart(2,'0')} ${ampm.uppercase()}. Time to wake up.")
        }

        // "remind me to X in 10 minutes / 2 hours"
        Regex("""remind me to (.+?) in (\d+)\s*(minute|hour)""").find(t)?.let { m ->
            val title = m.groupValues[1].trim().replaceFirstChar { it.uppercase() }
            val n = m.groupValues[2].toInt()
            val unit = m.groupValues[3]
            val mins = if (unit.startsWith("hour")) n * 60 else n
            return Intent.SetReminder(delayMinutes = mins, title = title)
        }

        // "remind me to drink water every 2 hours"
        Regex("""remind me to (.+?) every (\d+)\s*(minute|hour)""").find(t)?.let { m ->
            val title = m.groupValues[1].trim().replaceFirstChar { it.uppercase() }
            val n = m.groupValues[2].toInt()
            val unit = m.groupValues[3]
            val mins = if (unit.startsWith("hour")) n * 60 else n
            return Intent.SetRepeatingReminder(title = title, intervalMinutes = mins)
        }

        // "remind me to X at 8 pm"
        Regex("""remind me to (.+?) at (\d{1,2})(?::(\d{2}))?\s*(am|pm)""").find(t)?.let { m ->
            val title = m.groupValues[1].trim().replaceFirstChar { it.uppercase() }
            val h = m.groupValues[2].toInt()
            val min = m.groupValues[3].toIntOrNull() ?: 0
            val ampm = m.groupValues[4]
            val hour24 = if (ampm == "pm" && h != 12) h + 12 else if (ampm == "am" && h == 12) 0 else h
            val now = LocalDateTime.now()
            var target = now.withHour(hour24).withMinute(min).withSecond(0)
            if (target.isBefore(now)) target = target.plusDays(1)
            val delay = ChronoUnit.MINUTES.between(now, target).toInt()
            return Intent.SetReminder(delayMinutes = delay, title = title)
        }

        if (t.contains("what's on my schedule") || t.contains("what do i have tomorrow") || t.contains("morning briefing")) {
            return Intent.MorningBriefing
        }
        if (t.contains("show my tasks") || t.contains("list tasks")) return Intent.ListTasks
        Regex("""open (\w+)""").find(t)?.let { m -> return Intent.OpenApp(m.groupValues[1]) }
        Regex("""(turn on|turn off) (bluetooth|flashlight|wifi)""").find(t)?.let { /* handled as Unknown -> Ollama tool */ }

        return Intent.Unknown(raw)
    }

    fun scheduledTimeForAlarm(time: LocalTime): Calendar {
        val cal = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, time.hour)
            set(Calendar.MINUTE, time.minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
            if (timeInMillis <= System.currentTimeMillis()) add(Calendar.DAY_OF_YEAR, 1)
        }
        return cal
    }
}
