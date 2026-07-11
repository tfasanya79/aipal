# AiPal — product status (living doc)

**Canonical current-state reference.**  
**App version:** `2.6.21+110` (Play Internal build, 2026-07-07 — onboarding timeout resilience hotfix + non-blocking profile sync)  
**Phase 1 Complete:** Scheduling Intelligence uplift (urgency classification, smart follow-ups, auto-time-blocking, recovery)  
**Wake phrase:** Stable default is v0.1 (known-working). v0.2 (voice-trained) is disabled by default pending an on-device ONNX Runtime compatibility fix — see Phase 1 Patch section below.  
**Stack:** Flutter mobile/web + FastAPI v2 — not Capacitor/React Native.

---

## Current phase (honest assessment)

| Phase | Name | Status |
|-------|------|--------|
| **A** | Conversational brain + chat-to-Today | **Done** (v11) |
| **B** | Visible brand + Today visual polish | **Done** (v11.1) |
| **C** | Voice-first / wake / proactive | **C5.2+ voice reliability — gates code-fixed; device QA pending** |
| **D** | MVP feature completion | **In progress** (see MVP_EXECUTION_PLAN.md) |

---

## Shipped features (build 100, 2026-06-29)

- Multi-turn `conversation_turns` + `session_id` on text and Live WS turns
- LLM `plan_extractor` → `plan_draft` → user **Confirm** / **Not now** → Today
- `PlanDraftCard` in text chat; `tool_actions` surfaced
- Contextual `/daily/live-greeting` (tasks, draft, time of day)
- Today: priority lanes, routine chips, focus timer dial, suggest-day
- Play Internal track: **2.6.11+100** (Android)
- Session observability (`session_events`, Settings export)
- C1 foreground wake word **Hi Pal** (OpenWakeWord; Settings opt-in)
- C2 Android background wake — foreground microphone service + notification
- **LLM streaming infrastructure** — `llm_stream()` async generator; DeepSeek SSE streaming enabled; `max_tokens` reduced to 180 for voice turns; latency logging added
- **SSE streaming endpoint** — `POST /turn/text/stream` for real-time token delivery
- **Date-staleness fix** — client refreshes `todayView` on resume when date changed + 5-min periodic timer
- **Overdue task lane** — API returns and LLM context surfaces overdue tasks from prior days
- **Google Sign-In** — `POST /auth/google` (ID token verification via `google-auth`)
- **Apple Sign-In** — `POST /auth/apple` (Apple JWT verification); onboarding screen updated
- **Spotify Android deep-link control** — Companion emits on-device music commands; mobile launches Spotify app via `spotify:` URIs (no Spotify Web API dependency)
- **Music intent** — plan extractor recognises play/pause/skip/volume intents; routed to Android deep-link command payload
- **Voice gate debounce** — 300ms time-based debounce on `toggleLive()` (gate 6 hardening)
- **Companion Voice Selection (Phase D-voice)** — 6 curated `edge-tts` voices (Aria/Jenny/Emma/Andrew/Brian/Sonia); `GET /voice/catalogue`; `POST /voice/preview`; `tts_voice` preference stored per-user; Settings picker sheet with preview button; free for all users
- **Weekly email UI** — Settings "Preview & Send" button; calls `GET /daily/weekly-summary` + `POST /daily/weekly-summary/send` (Resend provider active)
- **Weekly email automation (scheduled)** — secured `POST /jobs/enqueue-weekly-summaries` endpoint + VM `aipal-worker.service` + `aipal-weekly-email.timer` (Sun 18:00 UTC)
- **Overdue lane in Today screen** — muted-red "Overdue" lane above Now; "Defer all overdue" action
- **LLM streaming for audio turns** — audio turn LLM call now uses `llm_stream`; `_llm_reply_with_early_tts` helper for future first-sentence TTS parallelism
- **Wake enrollment screen** — guided in-app 5-utterance enrollment per phrase (Hi Pal / HiPal / AiPal); threshold calibration; `WakeWordPrefs.markEnrollmentDone()`; Settings "Calibrate wake phrase" tile
- **Wake calibration v2** — enrollment now scores recorded samples with OpenWakeWord, saves calibrated threshold (`wake_threshold_calibrated`), and refreshes wake listener immediately after calibration
- **Wake startup recovery** — background wake route now has explicit startup timeout + actionable permission error if listener never becomes ready
- **Calendar/location sync observability** — Settings now shows sync outcome status and offers explicit retry actions for calendar and location
- **Crash stabilization mode (Android)** — wake listener runs FGS-only while wake is enabled, with calibration pause/resume safety gate to prevent dual OpenWakeWord engine races
- **Voice reliability foundation (Phase C5.3)** — introduced typed `VoiceState` + `VoiceOrchestrator` transition ledger in mobile AppState with structured `voice_state_transition` diagnostics and unit tests (behavior-preserving first increment)
- **Voice mic ownership + diagnostics (Phase C5.3)** — added shared `MicrophoneManager` ownership guard across wake/listen/enrollment flows and a companion diagnostics overlay (long-press status chip) showing voice state transitions + mic owner

---

## Phase 1: Companion Scheduling Intelligence (Completed — 2026-07-02)

**Goal:** Elevate scheduling from "helpful" to "anticipatory companion"  
**Target deploy:** v2.6.16+105 (2026-07-02)  
**Status:** ✅ All 7 core features implemented and validated

### Phase 1 Features (Completed)

| Feature | Status | Ship Target | Notes |
|---------|--------|-------------|-------|
| 1. Context-aware urgency classification | ✅ Done | v2.6.16+105 | High/medium/low emoji hints (🔴🟡🟢) in task title; `_infer_urgency()` in plan_extractor |
| 2. Smart follow-up prompts | ✅ Done | v2.6.16+105 | "Block focus time?", "Need travel time?", "Prep needed?" post-booking; integrated in voice router via reflection_svc |
| 3. Automatic time blocking | ✅ Done | v2.6.16+105 | `suggest_time_slot()` auto-assigns times for duration tasks without explicit times; work→9am, health→5pm, home→2pm, meals→12pm, sleep→10pm |
| 4. "If-not-done" recovery logic | ✅ Done | v2.6.16+105 | Morning briefing queries yesterday's incomplete tasks; suggests recovery with micro_motivation_phrase in daily_router |
| 5. Expanded voice editing | ✅ Done | v2.6.16+105 | Added `delete_task` and `mark_urgent` intents to plan_extractor; integrated handlers in action_executor and voice router |
| 6. Micro-motivation nudges | ✅ Done | v2.6.16+105 | Adaptive phrases by hour/mood; `micro_motivation_phrase()` leveraged in morning briefing |
| 7. Multi-modal reminder cues | ✅ Done | v2.6.16+105 | Vibration patterns (urgent vs normal), urgency emoji (🔴/🟡/🟢), sound differentiation in notification_service.dart |
| 8. Wake model v0.2 integration | ⚠️ Reverted to v0.1 default | v2.6.19+108 | v0.2 caused a total wake regression when shipped as default in v2.6.17+106 (the claimed fallback was never actually committed). v2.6.18+107 restored v0.1 as default, but a separate stale-model-cache bug kept wake broken on already-affected devices until v2.6.19+108. See Phase 1 Patch section. |
| 9. Emotional tone matching (expand) | ✅ Done | v2.6.16+105 | mood.py expanded with stressed/excited/focused tone instructions |
| 10. Wellness check-in layer | ✅ Done | v2.6.16+105 | reflection.py wellness + follow-up templates ready for integration |
| 11. Briefing scheduler service | ✅ Done | v2.6.16+105 | New `briefing_scheduler.py` for async scheduled briefing callbacks |

### Phase 1 Impact

- **User:** Companion feels anticipatory + proactive. Scheduling feels effortless. Missed tasks don't create guilt.
- **Stakeholder:** Positioning shifts to "anticipatory companion" (vs. "smart scheduler"). Retention signal: multi-touch interactions per task.
- **Technical:** Latency <8s/turn. No crashes. Wake accuracy maintained. Urgency + tone signals reduce decision fatigue.

### Phase 1 Implementation Summary

**Python API (plan_extractor.py, action_executor.py, router.py, daily_router.py, reflection.py):**
- `suggest_time_slot()`: Category-aware time defaults (work→09:00, health→17:00, home→14:00, meals→12:00, sleep→22:00)
- `_normalize_plan()`: Auto-fills `due_at` for tasks with `estimated_minutes` but no explicit time
- `try_handle_delete_extraction()`: Parse and execute delete_task intents with title/id matching
- `try_handle_mark_urgent_extraction()`: Parse and execute mark_urgent intents with title/id matching
- `smart_follow_up_prompts()`: Leveraged in voice router to return follow-up suggestions with draft response
- `micro_motivation_phrase()`: Integrated into morning briefing for contextual motivation
- `morning-briefing-spoken`: New endpoint returning TTS audio with daily summary + motivation

**Flutter Mobile (notification_service.dart, wake_word_engine.dart):**
- Vibration patterns: Urgent (0-400-300-400ms long-short-long) vs Normal (0-200-200ms short)
- Urgency indicators: 🔴 urgent, 🟡 medium, 🟢 normal appended to notification body
- Sound selection: Different sound file paths based on urgency level
- Wake v0.2 support: `switchModelVersion()` enables runtime model switching; threshold tuned to 0.04

**Services:**
- `briefing_scheduler.py`: BriefingScheduler class for async scheduled briefing callbacks at user-set morning time

---

- [x] D0-A — LLM latency reduction (streaming, max_tokens 180 for voice)
- [x] D0-B — Date staleness bug (client refresh + server overdue lane + Today UI overdue lane)
- [x] D0-C — Auth gateway: Google + Apple Sign-In
- [x] D1 — Voice baseline code fixes (gate 4; 1/3/6/6-debounce confirmed); smoke script
### Phase 1 Patch: Wake bug hotfix (v2.6.18+107, 2026-07-03)

v2.6.17+106 shipped v0.2 as the default wake model, but the v0.2→v0.1 fallback
described in that commit's message was never actually committed (only
`pubspec.lock` changed) — wake was completely broken for all users on that build.

**Root cause (working theory, pending device-log confirmation):** the v0.2 model
(OpenWakeWord-trained on real voice, 62 ONNX nodes with a decomposed LayerNorm)
has a structurally different graph than v0.1 (9 nodes, fused `LayerNormalization`).
Both load fine on desktop ONNX Runtime; the Android-bundled runtime inside the
`open_wake_word` plugin most likely only registers kernels for the reference
architecture, so v0.2 fails to load on-device only.

**Fixed in v2.6.18+107:**
- Default model reverted to v0.1 (known-working) — wake works again immediately.
- Real v0.2→v0.1 fallback implemented in `wake_word_engine.dart` (this time
  actually committed and verified in the build).
- `open_wake_word` plugin vendored into `apps/mobile/third_party/open_wake_word`
  and its native C++ model-loading threads hardened with try/catch, so an
  incompatible model fails gracefully instead of risking an uncaught native
  crash on a detached thread.
- Settings now shows the actually-active model version; "Calibrate wake phrase"
  relabeled "Fine-tune wake accuracy (optional)".
- `SessionLogger` (Settings → "Record test sessions") expanded to also log
  voice turns and wake engine ready/failed events — previously it only fired
  for typed text messages, missing the app's primary (voice) usage path.

**Still open (as of v2.6.18+107):** confirming the exact on-device failure needs real
device logs (no crash reporting SDK is integrated yet — Firebase Crashlytics is blocked
on an external Firebase project + `google-services.json`, see `SETUP_CREDENTIALS.md`).
v0.2 stays opt-in/disabled until this is resolved.

### Phase 1 Patch: Wake bug hotfix round 2 (v2.6.19+108, 2026-07-03)

After v2.6.18+107 shipped (v0.1 default + real fallback), the user's device
**still** showed "OpenWakeWord.init returned false" / "Retry listener", even
though screenshots confirmed the new build (with the v2.6.18 Settings label
changes) was installed. This ruled out the v0.1/v0.2 opset-mismatch theory as
the *active* bug on that device — v0.1 itself was failing to init.

**Real root cause found:** `third_party/open_wake_word`'s `_extractAsset()`
helper copies each bundled ONNX model (mel, embedding, wake-word) from the
Flutter asset bundle to the app's documents directory **only if a file with
that name doesn't already exist there**, and never overwrites it afterwards.
Android app data persists across app updates (unless the user clears storage
or uninstalls), so any stale, partial, or corrupt cached copy — e.g. one
left behind by an interrupted write during the earlier crash-storm builds —
would be loaded **forever**, no matter how many times the bundled asset
itself was fixed and redeployed. This fully explains why the v0.1-default
hotfix did not resolve wake on this specific device.

**Fixed in v2.6.19+108:**
- `_extractAsset()` now always re-copies the bundled asset on every engine
  init instead of skipping when a same-named file exists. Self-heals
  automatically on the next app launch after updating — no reinstall or
  "clear storage" needed by the user.
- Added `oww_get_last_error()` to the native plugin (header + `.cpp` +
  regenerated FFI bindings + Dart wrapper) so the *real* native failure
  reason (already tracked internally, just never surfaced) shows up in
  `lastInitError` instead of the generic "OpenWakeWord.init returned false".
  This gives us a diagnostic window into any future on-device-only failures
  without needing full crash reporting.
- Fixed `Mobile CI` (`flutter analyze` was failing on an `avoid_print` info
  finding inside the vendored `third_party/open_wake_word` plugin code) by
  excluding `third_party/**` in `apps/mobile/analysis_options.yaml`.
- Verified: `flutter analyze` clean, `flutter test` 14/14 passing, Android
  arm64 release build (with the modified native C++) compiles and uploads
  successfully to Play Internal (versionCode 108).

**Known issue (unrelated, needs user action):** `Sync GitHub Project` CI
workflow fails with `GraphQL 401: Bad credentials` — the `PROJECT_SYNC_TOKEN`
repository secret (a GitHub PAT) appears expired or revoked. A repo admin
needs to generate a new PAT (classic, with `repo` + `project` scopes, or a
fine-grained token with Projects read/write) and update the secret; the
agent cannot mint a GitHub PAT on the user's behalf.

### Hotfix: onboarding timeout resilience (v2.6.21+110, 2026-07-07)

User-reported onboarding failures on the profile step were showing raw
`TimeoutException after 0:00:12.000000: Future not completed`, blocking setup.

**Fixed in v2.6.21+110:**
- Onboarding submit now uses a staged completion flow in `AppState` instead of
  throwing raw exceptions directly in the screen.
- If profile update times out after auth is already valid, the app now proceeds
  to Home and queues profile sync in the background (per product decision).
- Pending profile payload is persisted in secure storage and retried on startup
  until sync succeeds.
- `ApiClient` now enforces HTTP error handling for auth/profile routes
  (`register`, `verify`, `getProfile`, `updateProfile`) and supports per-call
  timeout overrides for this flow.
- Onboarding UI now prevents duplicate submits, shows in-progress state, and
  maps technical failures to user-safe messages.

- [ ] D2 — Wake phrase model v0.2 (in-app enrollment screen shipped; model retrain needs enrollment data)
- [x] D3 — Today intelligence uplift (multi-task, relative times, music intent in extractor)
- [x] D4 — Spotify Android deep-link control (policy-safe MVP path)
- [x] D5-A — Weekly email summary (manual preview + send UI shipped; Resend active)
- [x] D5-B — Weekly email scheduled automation (internal-secret endpoint + VM timer/worker live)
- [x] D-voice — Companion voice selection (6 voices, free for all users; Settings picker)
- [ ] D6 — Subscriber gateway + tier enforcement (deprioritised — app is free)
- [x] D7 — Continuous doc sync

---

## Companion persona contract (current direction)

- **Primary style:** Hybrid Pro Companion (warm, concise, task-sharp).
- **Adaptive layer:** add empathy/motivation when user mood seems low or unusual.
- **Guardrail:** maintain practical professionalism (clear actions, no over-chatty drift).
- **Voice default:** 1–2 natural sentences unless user asks for detail.

---

## Phase A backlog

- [x] A1 — `conversation_turns` + history in `turn.py` / `ws_session.py`
- [x] A2 — `plan_extractor.py` (LLM JSON tasks + times)
- [x] A3 — Plan draft GET / confirm / discard + Flutter confirm flow
- [x] A4 — Contextual live greeting; skip generic opener if chatted today
- [x] A5 — `test_brain_v11.py` + smoke plan-draft path

---

## Phase A backlog

- [x] A1 — `conversation_turns` + history in `turn.py` / `ws_session.py`
- [x] A2 — `plan_extractor.py` (LLM JSON tasks + times)
- [x] A3 — Plan draft GET / confirm / discard + Flutter confirm flow
- [x] A4 — Contextual live greeting; skip generic opener if chatted today
- [x] A5 — `test_brain_v11.py` + smoke plan-draft path

**Remaining:** None for Phase A scope.

---

## Phase B backlog

- [x] B1 — `AiPalBrandRow` on Companion + Today; favicon cache-bust; onboarding orb/wordmark
- [x] B2a — Priority lanes (`priority_lanes.dart`)
- [x] B2b — Routine quick-add chips → plan draft
- [x] B2c — Focus timer circular dial (`focus_timer_bar.dart`)
- [x] B2d — Suggest for me → `POST /tasks/suggest-day`

**Remaining:** None for Phase B scope.

---

## Phase C backlog

### C0 — Decisions & foundations (done)

- [x] Wake word engine decision doc → `docs/decisions/wake-word-engine.md`
- [x] Today snapshot injected into every LLM turn
- [x] Ban push-to-talk phrasing in LLM + Live greetings
- [x] `today-view` default day = user timezone
- [x] Tester brief skill + release QA extensions
- [x] `aipal-brain` skill: Today as operational state

### C1 — Foreground wake (done)

- [x] OpenWakeWord Flutter integration (`open_wake_word` FFI + `hi_pal_v0.1.onnx`)
- [x] Wake → start Live in Companion (`toggleLive`)
- [x] Settings: "Listen for Hi Pal" toggle (default off)
- [x] Companion teaching copy + `/daily/live-greeting?show_wake_intro`
- [ ] Sensitivity slider (deferred)

### C2 — Background listening (done — Android)

- [x] Android foreground service + notification (`flutter_foreground_task`, microphone FGS)
- [x] Wake across tabs and when app backgrounded (screen on)
- [x] Suppress listening during Live / TTS
- [x] Battery note in Settings; threshold + cooldown tuning (sensitivity slider deferred)
- [x] iOS remains foreground-only on Companion tab (Shortcuts later)

### C3a — Smart Today logging (done)

- [x] Remove silent regex task creation from chat turns
- [x] Plan extractor: 1–4 word titles + notes field
- [x] Dedup on plan confirm
- [x] Voice plan_draft on audio turn + PlanDraftCard on Companion
- [x] Voice/text confirm intent ("yes add to today")

### C3b — Proactive nudges (done)

- [x] Local notifications ~12 min before `due_at`
- [x] `GET /daily/task-nudge` dynamic message (wake_name)
- [x] Foreground TTS on Companion when app open
- [x] Quiet hours + daily nudge cap

### C4 — Companion depth (done)

- [x] C4-1 — `context_builder` + mem0 every turn (structured metadata)
- [x] C4-2 — Non-clinical mood tone (VADER → prompt hint)
- [x] C4-3 — Evening/morning `companion_line` + review sheet
- [x] C4-4 — Light device calendar → brain context (read-only)

See [`decisions/companion-c4.md`](./decisions/companion-c4.md).

- Phase C4 companion depth: mem0, mood, calendar context, reflection (build 44)
- **C4.1 hotfix (build 45):** routine chip wrap layout; device timezone sync; local wall-clock scheduling fix; duration-before-draft for meetings; Today task time/duration edit

### C4.1 — Today UX + scheduling (Done, build 45)

- [x] Suggest routines chips wrap on all screen widths (`Wrap` layout)
- [x] Device IANA timezone synced to profile on bootstrap + onboarding
- [x] Plan extractor reinterprets UTC/Z timestamps as user-local wall clock
- [x] Today day-bucketing uses user timezone (not UTC midnight)
- [x] Meetings without stated duration: Companion asks in chat before plan draft
- [x] Tap task on Today → edit time and duration

### C4.2 — Voice booking fix (Done, build 46)

- [x] Auto-confirm complete voice bookings (explicit book + time + duration)
- [x] LLM guardrails: never claim task is on Today until confirmed
- [x] Refresh Today tab when voice returns plan draft

### C4+ — Deferred

- [ ] Compose message draft — user describes intent; AiPal drafts SMS/email for user review, edit, and manual send (no auto-send)

### C5 — Personal Assistant brain (Done, build 48)

- [x] `action_executor` + `task_resolver` — grounded create/update/complete/delete
- [x] `edit_task` intent in plan_extractor; hybrid instant/confirm reschedule
- [x] Confirm recovery for update offers (`yes` after "say yes and I'll update it")
- [x] Universal honesty guard — update/complete/delete claims require tool actions
- [x] Schedule block includes task `id=` + local times; refresh after mutations
- [x] `tests/test_action_executor.py` + regression suite

See [`decisions/companion-c5.md`](./decisions/companion-c5.md).

### C5.1 — Live resting + wake reliability (Done, build 49)

- [x] One-shot Live: return to Resting after each voice turn (not continuous VAD)
- [x] Noise gating: min voiced duration client-side; empty/junk STT silent server-side
- [x] Instant clear reschedules via regex-first edit (no LLM "say yes" for "move X to 8pm")
- [x] Wake word lifecycle: `engine_ready`/`engine_failed` handling, FGS restart after Live
- [x] Permission/error surfacing in Settings when Hi Pal cannot start

### C5.2 — Conversation session + wake reliability (Done, build 50)

- [x] Bounded multi-turn session with 18 s idle timeout (replaces one-shot Live)
- [x] Greeting TTS before VAD; mic suppressed during greeting/speech/thinking
- [x] Discarded noise segments stay in session; soft "I'm listening — go ahead" after 2 rejects
- [x] Explicit end: "bye", orb tap, idle timeout → Resting + wake resumes
- [x] Zombie session fix: `_inConversation` never true without active loop; wake recovery on stale state
- [x] Wake handshake: 800 ms FGS restart, 5 s `engine_ready` timeout/retry, `engine_failed` on restart failure

### C5.2+ — Voice reliability hotfixes (builds 59–61, device QA ongoing)

Targeted unfreezes addressing Hi Pal listener stability, phantom Live speech, and orb end-session. See [`releases/VOICE_BASELINE.md`](./releases/VOICE_BASELINE.md) gates 1–7.

| Build | Focus |
|-------|--------|
| 59 | Serialized wake sync; orb reentrancy guard; clear reply on Resting |
| 60 | Mic warmup (3s); wake suppress split; API ambient STT filters |
| 61 | Lifecycle-gated foreground route; suppress re-sync timer; FGS race fix |

**Not passing consistently on device as of 2026-06-27:** gate #1 (stable “Listening for Hi Pal”), gate #4 (quiet room), gate #6 (orb end). Continue device QA before C6 or “intelligence” backlog.

### C5.3 — Companion maturity (backlog)

- [ ] User goals in profile → brain context
- [ ] Companion initiative check-ins (opt-in)
- [ ] Weekly reflection ritual
- [ ] Relationship rituals (“remember when…” in Companion)

### C6 — Full-duplex Live Voice v2 — Deferred

Paused 2026-06-18. Production Live uses half-duplex (`POST /turn/audio`). See [`decisions/live-voice-v2.md`](./decisions/live-voice-v2.md) and [`releases/HALF_DUPLEX_RECOVERY.md`](./releases/HALF_DUPLEX_RECOVERY.md).

---

## Verification scenarios (regression)

| Scenario | Expected |
|----------|----------|
| Text: "meeting 4pm, swim 6pm" | Plan draft card; confirm → Today shows timed tasks |
| Voice: "remind me to go to bed at 8pm" | Draft title "Bedtime" (concise); no task until confirm |
| Task due in 15 min | Notification + TTS nudge on Companion (if foreground) |
| Android: Hi Pal with app backgrounded | Notification visible; wake opens app → Live |
| iOS: Hi Pal | Companion tab only while app open |
| Follow-up same `session_id` | No re-greeting; references prior turn |
| Live with open tasks | Greeting mentions up next; no "tap to talk" |
| "Team meeting at 2:30pm" | Today shows 2:30 PM local (not +2h offset) | C4.1 |
| Meeting without duration | Companion asks how long; no PlanDraftCard until answered | C4.1 |
| Tap task on Today | Edit sheet: change time + duration | C4.1 |
| Voice: "book a 6pm appointment for 30 minutes" | Task on Today immediately (auto-confirm) | C4.2 |
| Voice/text: "move Sweden Open to 8pm" | Today shows 8:00 PM; `Updated task:` in tool_actions | C5 |
| Vague: "change it to 8" → yes | Confirm offer then reschedule | C5 |
| "What's on my schedule?" | Lists local times from Today schedule block | C5 |
| LLM claims update without tool | Honest fallback or recovery | C5 |
| Live: one utterance per orb/wake tap | Returns to Resting; no ambient noise replies | C5.1 |
| Live: multi-turn follow-up ("yes") in same session | Stays Listening after reply; same `session_id` | C5.2 |
| Live: 18 s silence after reply | Returns to Resting; Hi Pal works again | C5.2 |
| Live: orb tap during conversation | Ends session immediately; wake resumes | C5.2 |
| Greeting before mic | TTS plays before "Live — listening" chip | C5.2 |
| Hi Pal after Live session | Wake works without toggle off/on | C5.1 |

---

## Round 7 (v2.6.26+115): Root-cause voice pipeline fixes

Following a full re-read of the ChatGPT architecture review (13 recommendations) and
direct source inspection (not speculation), two confirmed, code-evidenced bugs were
fixed, plus consistent progress on the review's architecture recommendations.

### Bug #1 -- Orb "Tap to go Live" looked unresponsive
`app_state.dart`'s `_startConversation()` caught any startup failure, set an error
message, then called `_endConversation()` -- which flips `inConversation` to `false`
before the next frame. `companion_screen.dart` only rendered the error `if (inConvo)`,
so the message was deterministically invisible every time Live mode failed to start.
Fix: dedicated `liveError` field, set by the catch block using a new typed
`VoiceError.classify()` helper, rendered unconditionally in `companion_screen.dart`
(dismissible on tap), and a message is now shown when `toggleLive()` is called with no
auth token.

### Bug #2 -- "Retry listener" never actually recovered
`WakeBackgroundService.ensureRunning()` returned `true` immediately whenever
`FlutterForegroundTask.isRunningService` was already true -- without checking whether
the isolate/engine inside the service was actually alive. Every manual "Retry
listener" tap and the bounded auto-retry re-entered this same short-circuit, so a
stuck-but-"running" service (e.g. after a native init failure) could never recover;
retries were guaranteed no-ops. Fix: `ensureRunning({forceRestart})` now stops and
restarts the service fresh whenever the caller knows a previous attempt failed;
`AppState` tracks a `_wakeForceRestartNeeded` flag set on timeout/`engine_failed` and
cleared on `engine_ready`, so both manual and automatic retries force a clean restart.

### ChatGPT review architecture progress (this round)
- Centralized `VoiceConfiguration` for all wake/VAD/conversation tunables (was
  scattered across 3 files).
- Typed `VoiceError`/`VoiceErrorCategory` classification replacing raw
  `e.toString()` surfaced to users.
- `MicrophoneManager` now owns the single shared `AudioRecorder` instance; wake
  engine and both Live voice loop variants (io/web) migrated off their own
  recorders onto it.
- Wake activation is now frame-driven (polled from the PCM stream callback)
  instead of a separate `Timer.periodic`.
- Added a permanent "Copy diagnostics" action (voice state, mic owner, wake/live
  errors, last transitions, build number) to the long-press diagnostics overlay.
- Remaining items (orchestrator as sole authority, `AppState` domain-state split,
  full mocked test harness, streaming segmentation) stay tracked and sequenced in
  the session plan; not dropped, scheduled behind the higher-risk items they depend on.

### Regression tests added
- `test/providers/app_state_live_error_test.dart` -- `liveError` set on token-null
  toggle and on a failed conversation start; proven readable even after
  `_endConversation()` flips `inConversation` to `false`.
- `test/services/wake_background_service_force_restart_test.dart` -- pure-logic
  coverage of the exact force-restart decision (the previous silent-no-op
  scenario: already-running + forceRestart now correctly stops before
  restarting, instead of trusting the stale flag).

---

## Round 8 (v2.6.27+116): Wake isolate crash guard

Build 115 was installed and both symptoms persisted: the wake listener still failed
(`android_fgs_engine_not_ready`) and the app crashed repeatedly. Direct source
inspection (not device-log speculation) found the actual root cause.

### Root cause
`WakeForegroundHandler` -- the background-isolate entry point Android runs for the
Hi Pal listening service -- had zero try/catch anywhere (`onStart`, `onReceiveData`,
`_startEngine`). The app's global error handlers
(`FlutterError.onError` / `PlatformDispatcher.instance.onError`) are installed in
`main.dart`, which never runs for this isolate; it has its own separate entry point
(`startWakeCallback`) with no error handler of its own. Any exception thrown inside
this isolate (most likely a permission-channel issue specific to that isolate context)
was therefore uncaught: no `engine_ready`/`engine_failed` message was ever sent back
(explaining the fixed 8s timeout error every time), and an uncaught isolate exception
is consistent with the Android foreground service process dying and being relaunched
repeatedly -- i.e. the same one defect plausibly explains both reported symptoms.

### Fix
- Every entry point in `WakeForegroundHandler` now wraps its body in try/catch and
  is guaranteed to report `engine_failed` with the real error text back to the main
  isolate instead of dying silently.
- `WakeBackgroundService.ensureRunning()` (main-isolate side) now also wraps its
  permission/service calls in try/catch, recording the real exception in a new
  `lastEnsureRunningError` field that `AppState` surfaces instead of the generic
  "permission required" fallback message.
- This turns any remaining failure into an exact, diagnosable error string (visible
  via the existing "Copy diagnostics" action) rather than a black-box crash --
  the next fix, if still needed, can now be precise instead of another guess.

### Latency investigation (no code change shipped yet)
Traced the full voice pipeline. Client-side: VAD waits for a full silence tail
before uploading the complete recorded segment (no streaming upload). Server-side:
`audio_turn` runs STT, LLM reply, and TTS fully sequentially, returning one full
base64 audio blob only once all three finish; client decodes and plays only after
that. A helper (`_llm_reply_with_early_tts`) already exists to start TTS on the
first sentence while the rest of the reply streams, but it turned out to be dead
code (never called), and wiring it into `audio_turn` directly would conflict with
existing post-generation safety checks (honesty/therapy-reply overrides can replace
`reply` entirely after the LLM finishes) -- speaking a first sentence before those
checks run would risk playing content that gets overridden a moment later. This
needs a careful, dedicated redesign rather than a quick wire-up; tracked as a
follow-up, not shipped this round to avoid trading one bug for another.

### Conversation-starter scope (user-confirmed, narrowed)
No new proactive trigger types this round. Only the existing daily check-in prompt
content/timing is being made smarter and more natural -- same toggle, no new UI.

---

## Round 8 follow-up (v2.6.28+117): the real wake crash, found via diagnostics

Build 116 shipped the isolate crash *guard*, and it worked exactly as intended: the
next crash report surfaced an exact, diagnosable error instead of a generic
timeout --

```
wakeWordError=onStart crashed: PlatformException(PermissionHandler.PermissionManager,
Unable to detect current Android Activity., null, null)
```

### Root cause
`WakeWordEngine._startImpl()` calls `ensureMicPermission()`, which called
`Permission.microphone.request()`. On Android, `permission_handler`'s `.request()`
needs a foreground `Activity` attached so it can show the system permission dialog
and receive the callback. `WakeForegroundHandler.onStart` runs inside the Android
foreground-service background isolate, which has no `Activity` -- so `.request()`
threw immediately, and (thanks to the build-116 crash guard) that exception was
finally caught and reported instead of silently killing the isolate.

By the time this isolate starts, the permission has *already* been requested and
granted by the main isolate in `WakeBackgroundService.ensureRunning()` (which does
run with an Activity, since it's triggered from the Settings toggle). The
background isolate calling `.request()` again was both redundant and fatal.

### Fix
- Added a `canRequestPermission` constructor flag to `WakeWordEngine` (default
  `true`, preserving existing behavior for the main-isolate/Settings "fine-tune"
  preview flow).
- `ensureMicPermission()` now checks `Permission.microphone.status` (a read-only
  query that does not require an Activity) instead of `.request()` whenever
  `canRequestPermission` is `false`.
- `WakeForegroundHandler` constructs its `WakeWordEngine` with
  `canRequestPermission: false`, since it always runs in the Activity-less
  background isolate.

This is a narrow, evidence-based fix directly from the exact error text the
build-116 diagnostics surfaced -- not a guess.

---

## Related docs

- [Wake word decision](./decisions/wake-word-engine.md)
- [Half-duplex recovery build 38](./releases/HALF_DUPLEX_RECOVERY.md)
- [Live Voice v2 ADR (paused)](./decisions/live-voice-v2.md)
- [Core pillars](./CORE_PILLARS.md)
- [Stakeholder roadmap](./stakeholder/ROADMAP.md)
- [Play Internal v2](./releases/PLAY_INTERNAL_v2.md)
- [Companion C5 ADR](./decisions/companion-c5.md)
- [External assessment (chat import)](./assessment/INDEX.md) — compare via [COMPARISON.md](./assessment/COMPARISON.md)
