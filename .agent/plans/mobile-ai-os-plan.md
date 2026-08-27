# VISION Mobile AI OS — Plan

**Goal:** Make VISION feel like a native phone AI OS, not a squeezed website. Clean, fast, voice/camera-first, with workspace/projects.

**Current state (verified `2026-08-26`):**
- `frontend/src/components/ChatView.tsx:94` — desktop `app-shell` with 280px sidebar, `composer` centered 850px. Mobile is responsive (`@media max-width:768px`) but not native: no swipe drawer, no bottom sheet, no haptics, no safe-area keyboard handling.
- `frontend/package.json:9` Next 16.3.2, no Capacitor/Tauri, no `android` bridge — `android/` is empty Gradle stub.
- Sidebar `ChatHistorySidebar` exists but no swipe, no search indexing, no folders.
- Voice `useVoiceInput.ts` + `VoiceMicButton.tsx` is tap-only, no hold-to-talk, no TTS queue.
- Image via `uploadAttachments` + paste/drop, no native Camera API or Live Vision.
- Code `WorkspacePanel.tsx` + `WebsitePreview` exist but not mobile-split, no version history.

**Constraints:** Keep `ollama` local, `127.0.0.1:8000` API already optimized for TTFT <1s (see `ai/services/agent.py:678`).

---

## Phase 1 — Core Native Experience (2-3 weeks) — Do first

**1. App Shell & Navigation** `src/components/AppShell.tsx`, `globals.css:99`, `ChatView.tsx`
- Bottom nav: Chat / Projects / Search / Profile
- Sidebar becomes swipe drawer: `framer-motion` drag, `☰` opens, swipe-left closes, backdrop blur, `env(safe-area-inset-*)`
- New component `MobileDrawer.tsx` + `useSwipe.ts`
- Composer fixed bottom: `composer-wrapper` with `padding-bottom: max(16px, env(safe-area-inset-bottom))` + keyboard `visualViewport` listener to avoid cover

**2. Composer Excellence** `ChatView.tsx:167`, `lib/conversations.ts:1`
- `Composer.tsx` extracted: `+` → bottom sheet (Image/File/Camera), `Auto ▾` → Fast/Think/Vision/Code/Agent (persisted `vision_mode`), hold `🎙` → waveform, release to send
- Single search: `searchConversations` already exists, add `cmdk` instant filter, debounce 150ms

**3. Voice Major** `hooks/useVoiceInput.ts`, `VoiceWaveform.tsx`
- Hold-to-talk: `onPointerDown` start, visual `Listening...`, `onPointerUp` send, haptics `navigator.vibrate(20)`
- TTS queue: `speechSynthesis` with Pause/Resume/Stop/Speed, per-message `▶ Speak` already in `ChatView.tsx:512`

**4. Chat Polish** `MarkdownRenderer.tsx`, `globals.css:181`
- Minimal bubbles (already), add follow-up chips `Explain simpler | Show example | Write code` as post-message actions
- Pull-to-refresh, haptics on send

**Acceptance:** Lighthouse mobile 95+, drawer <16ms, composer never hidden by keyboard on iOS/Android.

---

## Phase 2 — Power Features (3-4 weeks)

**5. Camera & Vision** New `CameraView.tsx` + `useCamera.ts`
- Native `getUserMedia` with `facingMode: environment`, capture → `uploadAttachments`, quick actions `[Analyze][Extract text][Find problems]`
- Live Vision (Phase 3 preview): `requestVideoFrameCallback` → 1fps `canvas.toBlob` → `moondream` via `ai/services/ollama_client.py`

**6. Code Workspace** `WorkspacePanel.tsx`, `WebsitePreview.tsx`
- Mobile split: `CodeWorkspace.tsx` with file tabs `index.html|styles.css|app.js`, `Preview` async iframe, `Copy|Download|Run`
- `Artifacts/Project` model: `ai_agent/models.py` add `Project` (FK User, files JSON, versions), `conversations_urls.py` add `projects/` CRUD, version history with diff

**7. Real Agent** `ai/services/tools.py`, `ai/services/agent.py:120`
- Permission sheet: `Allow Once | Always | Cancel` for `filesystem_write/terminal/delete`, undo via `workspace` version
- Progress UI already `agentSteps` in `ChatView.tsx:138` — extend to `✓ Opened | ● Applying | ○ Tests`

**8. Search & Memory** `lib/conversations.ts:92`, `learning/retrieval.py`
- Universal search: chats+files+projects via `Q(title__icontains) | Q(messages__content__icontains)` + FTS index
- Memory categories UI `MemoryPanel.tsx` already — add `Preferences|Projects|Decisions` tabs

---

## Phase 3 — Differentiation (4+ weeks)

Live camera streaming, Computer Use (`browser` tool via Playwright), Interactive Mermaid diagrams (`MermaidBlock` tap → explanation), Study Mode (Explain→Example→Quiz), Offline badge `● Local` at `ChatView.tsx:521` already `health.ollama.connected`, Model Status sheet.

---

## File Map

- `frontend/src/components/MobileDrawer.tsx` (new)
- `frontend/src/components/Composer.tsx` (extract from ChatView)
- `frontend/src/components/CameraView.tsx` (new)
- `frontend/src/components/CodeWorkspace.tsx` (new)
- `frontend/src/hooks/useSwipe.ts`, `useCamera.ts`, `useHaptics.ts` (new)
- `backend/ai_agent/models.py` — add `Project`, `ProjectVersion`
- `backend/ai_agent/urls.py` — add `projects/`, `camera/`
- `android/` — `Capacitor` wrapper: `npx cap add android`, bridge `getUserMedia` + `speechSynthesis`

---

## Risks & Decisions

- **Decision needed:** Capacitor vs PWA vs React Native? Recommend PWA first (instant), then Capacitor for Play Store.
- **Risk:** `ollama` on phone is desktop-only; mobile will be remote `127.0.0.1:8000` via tunnel — offline mode is desktop-only. Document clearly.
- **Risk:** Live Vision at 1fps will be hot — throttle to 0.5fps on mid devices.

## Next Step

If you approve Phase 1, I will start with `MobileDrawer + Composer` and `globals.css:158` safe-area fixes — ask to proceed.
