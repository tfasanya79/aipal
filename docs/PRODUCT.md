# AiPal — product status (living doc)

**Canonical current-state reference.** The Cursor plan file [aipal_brain_and_qa_ac51c760.plan.md](/home/dev/.cursor/plans/aipal_brain_and_qa_ac51c760.plan.md) captured the v11 brain milestone; it may be stale. Update **this file** when phases ship.

**App version:** `2.4.0+18` (see `apps/mobile/pubspec.yaml`)  
**Stack:** Flutter mobile/web + FastAPI v2 — not Capacitor/React Native.

---

## Current phase (honest assessment)

| Phase | Name | Status |
|-------|------|--------|
| **A** | Conversational brain + chat-to-Today | **Done** (v11) |
| **B** | Visible brand + Today visual polish | **Done** (v11.1) |
| **C** | Voice-first / wake / proactive | **In progress** (C1 + C2 + C3a/b shipped; C4 deferred) |

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
- Play Internal track: **2.4.0+18** (Android)
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

### C4+ — Deferred

- [ ] Richer mem0 retrieval every turn
- [ ] Calendar import
- [ ] Compose message draft — user describes intent; AiPal drafts SMS/email for user review, edit, and manual send (no auto-send)

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
| Today view near midnight (user TZ) | Tasks match user's local "today" |

---

## Related docs

- [Wake word decision](./decisions/wake-word-engine.md)
- [Stakeholder roadmap](./stakeholder/ROADMAP.md)
- [Play Internal v2](./releases/PLAY_INTERNAL_v2.md)
- Legacy charter: `legacy/Project-goal--explicit-plan-100-project-goal.md` (pre-Flutter; historical)
