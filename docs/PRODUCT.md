# AiPal — product status (living doc)

**Canonical current-state reference.** The Cursor plan file [aipal_brain_and_qa_ac51c760.plan.md](/home/dev/.cursor/plans/aipal_brain_and_qa_ac51c760.plan.md) captured the v11 brain milestone; it may be stale. Update **this file** when phases ship.

**App version:** `2.6.11+61` (see `apps/mobile/pubspec.yaml`)  
**Stack:** Flutter mobile/web + FastAPI v2 — not Capacitor/React Native.

---

## Current phase (honest assessment)

| Phase | Name | Status |
|-------|------|--------|
| **A** | Conversational brain + chat-to-Today | **Done** (v11) |
| **B** | Visible brand + Today visual polish | **Done** (v11.1) |
| **C** | Voice-first / wake / proactive | **C5.2+ voice reliability** (build 61 — device QA in progress) |

**Phase C naming:** In this doc, **C1** = foreground wake word, **C2** = Android background listening. That is **not** the same as plan file "Phase B" (logo/Today polish), which is **done** above.

---

## Shipped features

- Multi-turn `conversation_turns` + `session_id` on text and Live WS turns
- LLM `plan_extractor` → `plan_draft` → user **Confirm** / **Not now** → Today
- `PlanDraftCard` in text chat; `tool_actions` surfaced
- Contextual `/daily/live-greeting` (tasks, draft, time of day)
- Today: priority lanes, routine chips, focus timer dial, suggest-day
- In-app **AiPal** logo (Companion, Today header, onboarding)
- Release QA: `release-qa-agent.md`, `smoke-test.sh`, pytest brain tests
- Play Internal track: **2.6.11+61** (Android)
- Session observability for phased QA (`session_events`, Settings export)
- Today hero card (Reminders-style glanceable summary)
- C1 foreground wake word **Hi Pal** (OpenWakeWord; Settings opt-in)
- C2 Android background wake — foreground microphone service + notification
- Phase C prep: Today snapshot in turn context, timezone-aware today-view, voice UX copy rules

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
- Sensitivity slider (deferred)

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

## Related docs

- [Wake word decision](./decisions/wake-word-engine.md)
- [Half-duplex recovery build 38](./releases/HALF_DUPLEX_RECOVERY.md)
- [Live Voice v2 ADR (paused)](./decisions/live-voice-v2.md)
- [Core pillars](./CORE_PILLARS.md)
- [Stakeholder roadmap](./stakeholder/ROADMAP.md)
- [Play Internal v2](./releases/PLAY_INTERNAL_v2.md)
- [Companion C5 ADR](./decisions/companion-c5.md)
- [External assessment (chat import)](./assessment/INDEX.md) — compare via [COMPARISON.md](./assessment/COMPARISON.md)
