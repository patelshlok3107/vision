# VISION Android — JARVIS Mode

Native Android brain for VISION. Phone owns alarms/voice, Ollama owns reasoning.

## Quick Start
1. Open `android/` in Android Studio (Hedgehog+)
2. Set `baseUrl` in `data/remote/RetrofitModule.kt` -> your Django host (emulator: `10.0.2.2:8000`)
3. `Run > app` on device (Android 8+)

## What V1 Implements
- **Two brains**: `voice/LocalIntentParser.kt` handles `set alarm 7am`, `remind me in 10m`, `every 2 hours` offline. Complex -> `agent/VisionAgent.kt` -> `POST /api/ai/agent/chat/` -> Ollama.
- **Real alarms**: `alarm/AlarmScheduler.kt` uses `setExactAndAllowWhileIdle` + `AlarmReceiver` + `AlarmService` (TTS). Each alarm = unique `PendingIntent`. Reboot rescheduled via `BootReceiver`.
- **Voice**: `VoiceEngine` (SpeechRecognizer) + `TtsEngine` (streaming sentences) + `WakeWordManager` stub (swap to Porcupine in V2). Tap orb to talk, `Stop` interrupts.
- **UI**: Compose command center — ONLINE dot, reply card, pulsing orb, stats, next alarm, full list, text fallback.

## Key Files
- `voice/LocalIntentParser.kt` — emergency fallback, no LLM
- `alarm/AlarmScheduler.kt` — OS-level alarms, never overwritten
- `agent/VisionAgent.kt` — offline-first routing
- `ui/VisionHomeScreen.kt` — JARVIS glassmorphism dark UI

## Permissions
Grant on first launch: Microphone, Notifications, Alarms (`canScheduleExactAlarms`), Battery optimization -> Unrestricted for reliable alarms.

## Backend Contract
Uses existing Django `users/tasks/reminders/ai_agent` APIs. No backend changes needed except ensuring `api/ai/agent/chat/` and `api/ai/briefing/morning/` exist — already in `backend/ai/`.
For device LAN testing, run `python manage.py runserver 0.0.0.0:8000` and set phone baseUrl to `http://<your-ip>:8000/`.

## V2 Next
Porcupine wake-word `Hey VISION`, foreground `VisionVoiceService`, morning/night briefings at fixed alarms, calendar/phone intents.
