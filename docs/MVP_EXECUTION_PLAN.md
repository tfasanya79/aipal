# AiPal MVP Execution Plan

**Owner:** Development  
**Canonical version:** `docs/MVP_EXECUTION_PLAN.md` (this file)  
**Status doc:** [`docs/PRODUCT.md`](PRODUCT.md) — update after each phase  
**Last updated:** 2026-06-29  
**Build reference:** `2.6.11+100` (Play Internal)

> **Rule:** Every completed work item must be followed by a doc update in  
> `PRODUCT.md`, `DELIVERABLES.md`, and `ROADMAP.md` before marking the item done.

---

## Overview

This plan covers three categories of work in strict execution order:

| Category | Items |
|----------|-------|
| **Phase 0 — Critical bugs** | LLM latency, date staleness, auth gateway |
| **Phases 1–2 — Voice** | Voice reliability gate, wake phrase model |
| **Phases 3–5 — Features** | Today uplift, Spotify control, weekly email |
| **Phase 6 — Auth** | Subscriber gateway (Google + Apple sign-in) |
| **Ongoing** | Continuous doc sync after every change |

---

## Phase 0 — Critical Bug Fixes (do first)

These bugs degrade the daily experience and must be resolved before new features.

---

### 0-A — LLM Communication Latency

**Problem:** Every voice/text turn waits for the full LLM response before anything  
is sent back (no streaming). DeepSeek has a 60 s timeout; Ollama has 120 s.  
This creates unnatural pauses that break the "seamless conversation" feel.

**Root cause (code):**
- `apps/api/app/modules/brain/llm_provider.py` — `_deepseek_chat` and `_ollama_chat`  
  both wait for the full response body before returning.
- Plan extraction adds a **second serial LLM call** before the companion reply.
- `max_tokens=400` is generous; voice turns rarely need more than 150 tokens.

**Fix plan:**

1. **Enable streaming on DeepSeek** — use `httpx`'s `stream()` context manager with  
   `"stream": true` in the request. Return an async generator; stream tokens to the  
   caller over SSE or buffer the first sentence to start TTS immediately.

2. **Enable streaming on Ollama** — set `"stream": true` in the Ollama payload and  
   consume the NDJSON response line by line.

3. **Add a `llm_stream` helper** — `apps/api/app/modules/brain/llm_provider.py`  
   — signature: `async def llm_stream(messages) -> AsyncGenerator[str, None]`.  
   Existing callers keep `llm_chat` (which collects the stream for JSON extraction).

4. **Wire streaming to voice turns** — `apps/api/app/modules/voice/router.py`  
   audio/text turn path: once the first sentence ends (`.`, `!`, `?`), begin TTS  
   synthesis in parallel while the remainder streams in.

5. **Reduce `max_tokens` for voice turns to 180** — set `max_tokens=180` when  
   `channel="voice"`. JSON extraction turns keep 400.

6. **Add response-time logging** — log `time_to_first_token` and `total_latency_ms`  
   to `aipal.turn` logger for every LLM call so regressions are visible.

7. **Evaluate DeepSeek V3 vs V2.5** — run a latency benchmark (`scripts/llm-benchmark.sh`)  
   after streaming is live; switch model string if V3 is faster at same cost.

**Acceptance criteria:**
- Voice turn first-word-of-reply latency ≤ 900 ms on local WiFi (down from ~2-4 s).
- No regression on JSON extraction for plan extractor.
- Benchmark script committed to `scripts/llm-benchmark.sh`.

---

### 0-B — App Unaware of Real Date (date-staleness bug)

**Problem:** When the app is backgrounded overnight, the cached `todayView` is from  
the previous day. The Companion UI shows yesterday's tasks as "up next." The `Today`  
tab displays the wrong day's tasks until the user manually pulls to refresh.

**Root cause (code):**

1. **Mobile client — no date-change detection on resume:**  
   `apps/mobile/lib/main.dart` `didChangeAppLifecycleState` calls `syncDeviceCalendar()`  
   and `syncWakeListener()` on resume, but **not** `refreshTodayView()`.

2. **Mobile client — no midnight rollover guard:**  
   `AppState.todayView` (in `app_state.dart`) stores the response date-blind;  
   there is no comparison of the response's `summary.date` field with today's  
   local date to detect stale data.

3. **Server — no overdue-task surfacing:**  
   `apps/api/app/modules/today/tasks.py` `today_view` only queries `today + tomorrow`.  
   Tasks from prior days with `status="planned"` and `due_at` in the past are  
   silently excluded rather than surfaced as **overdue** in the context.

**Fix plan:**

1. **Client — refresh on resume if date has changed:**  
   In `apps/mobile/lib/main.dart` inside `didChangeAppLifecycleState` when state is  
   `resumed`, call `refreshTodayViewIfDateChanged()` — a new method on `AppState`  
   that compares the stored `todayView.summary.date` with today's local date string  
   and calls `refreshTodayView()` only if they differ.

2. **Client — add a periodic date-check timer:**  
   In `AppState.finishBootstrap()`, start a `Timer.periodic(Duration(minutes: 5), ...)`  
   that calls `refreshTodayViewIfDateChanged()`. Cancel on token loss.

3. **Server — add overdue task query to `today_view`:**  
   In `tasks.py`, add a third query `overdue_tasks` for:  
   `status IN ('planned','in_progress') AND due_at < <start_of_today_UTC>`.  
   Surface these in a new `TodaySections.overdue` list (empty by default for backward  
   compatibility). Expose in `TodayViewResponse`.

4. **Server — surface overdue context to LLM:**  
   In `context_builder.py` `format_today_schedule_block`, if `today_snap.sections.overdue`  
   is non-empty, prepend a line:  
   `"Overdue (carried from prior days): ..."` — so the Companion can acknowledge  
   these naturally rather than ignoring them.

5. **Mobile — show overdue lane in Today UI:**  
   Add an "Overdue" section above "Now" in `today_screen.dart`, styled in muted red,  
   with a "Defer all" action that calls `defer-open` for those tasks.

**Acceptance criteria:**
- App refreshes Today view automatically after midnight (verified manually).
- Overdue tasks appear in a separate lane in the Today UI and in LLM context.
- No overdue task is silently shown as "today's plan" in the Companion greeting.

---

### 0-C — Subscriber Authentication Gateway

**Problem:** Current auth is email magic-link only. For 2026, a consumer voice-first  
app must support social login for frictionless onboarding and subscriber management.

**Recommendation for 2026: Google Sign-In + Apple Sign-In on existing FastAPI stack**

| Option | Verdict |
|--------|---------|
| Firebase Auth | Good Flutter support; introduces Google infra lock-in. Reject. |
| Supabase Auth | Excellent PostgreSQL fit; adds managed cloud dependency. Consider for v3+. |
| Auth0 | Robust but expensive at scale. Reject for MVP. |
| **Native OAuth on FastAPI** | ✅ Leanest, zero vendor lock-in, keeps existing JWT |

**Why native OAuth:**  
The backend already has PostgreSQL + JWT (`python-jose`). Adding Google and Apple  
ID-token verification is ~80 lines of Python. No new managed service is needed.  
Flutter packages `google_sign_in` and `sign_in_with_apple` are well-maintained  
and free.

**Apple Sign-In is mandatory** for iOS App Store apps that offer social login.  
Google Sign-In is the highest-conversion option on Android in 2026.

**Fix plan:**

1. **API — add `google_auth` library to `requirements.txt`:**  
   `google-auth>=2.0` for ID token verification.

2. **API — new endpoint `POST /auth/google`:**  
   Accepts `{id_token: str}`. Verifies with Google's public keys via `google.oauth2.id_token.verify_oauth2_token`. Creates or finds User by `email`. Returns same `AuthResponse` (JWT) as magic link.

3. **API — new endpoint `POST /auth/apple`:**  
   Accepts `{identity_token: str, email: str | None}`. Verifies Apple JWT via  
   Apple's public keys (`PyJWT` + `cryptography` already in tree via `python-jose`).

4. **API — add `auth_provider` field to `User` model:**  
   `auth_provider: str = "magic_link"` — tracks `google`, `apple`, `magic_link`.  
   Add Alembic migration.

5. **API — `config.py` — add `google_client_id: str = ""`.**

6. **Mobile — add `google_sign_in` package to `pubspec.yaml`.**

7. **Mobile — add `sign_in_with_apple` package to `pubspec.yaml`.**

8. **Mobile — new `auth_service.dart`** with `signInWithGoogle()` and  
   `signInWithApple()` — each gets an ID token from the platform SDK and POSTs  
   to `/auth/google` or `/auth/apple`. On success, stores JWT as current token.

9. **Mobile — update `onboarding_screen.dart`** to show:  
   - "Continue with Google" button (primary)  
   - "Continue with Apple" button (iOS only, required)  
   - "Use email instead" (existing magic link flow, secondary)

10. **Subscriber gate (future-ready):** Add `subscription_tier: str = "free"` to  
    `User` model in the same migration. Enforce in a `require_subscription`  
    FastAPI dependency when premium features (Spotify, weekly email) are ready.

**Acceptance criteria:**
- User can sign in with Google on Android without entering an email.
- User can sign in with Apple on iOS.
- Magic link still works as a fallback on all platforms.
- `auth_provider` stored in DB per user.

---

## Phase 1 — Voice Reliability Gate

**Goal:** All 7 VOICE_BASELINE device QA gates pass consistently on the current  
Play build before any new voice features are added.

**Gates to pass** (`docs/releases/VOICE_BASELINE.md`):

| # | Scenario | Current status |
|---|----------|----------------|
| 1 | Hi Pal → speak → reply → 18s silence → Resting; Hi Pal works again | ❌ Not passing consistently |
| 2 | Hi Pal → reschedule → say yes in same session | ❌ |
| 3 | Tap orb → greeting plays → mic opens | ❌ |
| 4 | Ambient TV noise while Resting — no replies | ❌ |
| 5 | Mumble too quietly → soft prompt, not zombie Live | ❌ |
| 6 | Orb tap during conversation → Resting → Hi Pal works | ❌ |
| 7 | Task nudge while Resting → TTS only, mic stays off | ❌ |

**Fix plan:**

1. **Automate gate regression tests** — add `scripts/voice-gate-test.sh` that runs  
   the API smoke path for each gate scenario via `POST /turn/audio` with  
   pre-recorded WAV stubs. Gates 4 and 5 (ambient noise, mumble) use  
   existing `_is_low_signal_transcript` and `_is_nonsense_transcript` paths.

2. **Gate 1 fix — wake resume after 18s idle timeout:**  
   In `app_state.dart`, verify `_conversationIdleTimer` fires `_endConversation()`  
   cleanly and always calls `syncWakeListener()` after. Add unit test for the timer path.

3. **Gate 3 fix — greeting-before-mic ordering:**  
   Ensure `_awaitingGreeting` is `true` before the mic loop starts in  
   `live_voice_loop_io.dart`. Add a guard: if `_awaitingGreeting`, skip  
   the VAD activation until greeting TTS completes.

4. **Gate 6 fix — orb force-end robustness:**  
   In `toggleLive()` in `app_state.dart`, add a 300 ms debounce guard to prevent  
   double-tap re-opening. Verify `_inConversation` is reset to `false` and that  
   `syncWakeListener()` is called synchronously after session close.

5. **Gate 4 hardening — ambient STT suppression:**  
   Extend `_is_media_ambient_transcript` and `_is_nonsense_transcript` patterns in  
   `router.py` based on actual ambient transcripts logged in device QA sessions.  
   Pull `session_events` from the VM to extract real STT noise patterns.

6. **Document gate results** — after each fix, run manual device QA and update  
   `docs/releases/VOICE_BASELINE.md` with `Pass`/`Fail` per gate and build number.

**Acceptance criteria:**
- All 7 gates marked `Pass` in `VOICE_BASELINE.md` on a fresh Play build.
- Automated smoke script passes for gates 1, 2, 3, 7 in CI.

---

## Phase 2 — Wake Phrase Model ("Hi Pal", "HiPal", "AiPal")

**Goal:** Extend wake detection to cover natural phrase variants without degrading  
false-positive rate.

**Current state:**
- Only `hi_pal_v0.1.onnx` exists (trained with TTS synthesis only, "hi pal" phrase).
- "HiPal", "AiPal", "Hey Pal" are not detected.
- Model v0.2 retrain was deliberately deferred until gate #5 (Hi Pal reliability) passes.  
  Gate #5 must pass in Phase 1 before Phase 2 starts.

**Fix plan:**

1. **Collect real speaker recordings** — ask internal testers (Play Internal track)  
   to record 20–30 utterances each of "Hi Pal", "HiPal", "AiPal", "Hey Pal"  
   into a shared folder. Use Android voice memo app, 16 kHz mono WAV preferred.

2. **Update training script** — modify `scripts/train-hi-pal-wakeword.py`:
   - Add `"hi pal"`, `"hipal"`, `"aipal"`, `"hey pal"` as positive phrases.
   - Mix TTS-generated (espeak-ng) + real speaker recordings in 60/40 ratio.
   - Bump `N_POS` to 800, `N_NEG` to 2000.
   - Train a new `WakeNet` targeting ≥ 92% validation accuracy.
   - Export as `hi_pal_v0.2.onnx`.

3. **Update confidence threshold** — run threshold sweep (0.20–0.40) on a held-out  
   set of real speaker clips + ambient noise clips. Pick threshold that keeps  
   false-positive rate < 1 per 10 minutes in ambient noise.
   Update `WakeWordEngine.activationThreshold` in `wake_word_engine.dart`.

4. **Update `WakeWordEngine.wakePhrase`** static to `'Hi Pal / AiPal'` for UI copy.

5. **A/B test gate** — deploy v0.2 to Play Internal, run gates 1 + 4 + 5 again  
   before replacing v0.1 in the release build.

6. **Add `scripts/evaluate-wakeword.py`** — takes a WAV directory and reports  
   detection rate and false-positive count for a given model + threshold.

**Acceptance criteria:**
- All 4 phrase variants detected reliably (≥ 90% detection rate on tester clips).
- False-positive rate ≤ 1 per 10 minutes in ambient TV noise test.
- `hi_pal_v0.2.onnx` committed to `apps/mobile/assets/models/`.

---

## Phase 3 — Today Intelligence Uplift

**Goal:** Make Companion-managed Today more reliable, trustworthy, and testable.

**Fix plan:**

1. **Extraction reliability — edge cases:**
   - Multi-task messages ("meeting at 3, gym at 6, dentist tomorrow morning").
   - Relative times ("in 2 hours", "this afternoon", "next Monday").
   - Natural completions ("I finished the gym session").
   - Add `tests/test_extraction_edge_cases.py` covering each.

2. **Dedup improvement** — `plan_draft.py` `confirm_draft`:  
   Current dedup only blocks exact title + same day. Extend to fuzzy title match  
   (Levenshtein distance ≤ 2) and same `due_at` hour to prevent near-duplicate tasks.

3. **Clarifying question UX** — when `should_defer_draft` is true (meeting without  
   duration), the Companion currently asks in text. Add a follow-up path that  
   stores the partial draft and resumes when the user replies with a duration  
   (e.g. "1 hour") in the same session.

4. **Overdue acknowledgment** — once Phase 0-B overdue lane exists, add LLM  
   system context pattern: "You have N overdue task(s) from prior days. Name them  
   and offer to carry forward or discard."

5. **Regression suite expansion:**  
   Add to `apps/api/tests/test_brain_v11.py` and new `test_today_intelligence.py`:
   - Multi-task extraction with correct times.
   - Relative-time extraction ("in 2 hours" from a known `local_now`).
   - Dedup blocks near-duplicate confirm.
   - Overdue tasks appear in context when present.

6. **Today screen — task reorder by drag** — add `ReorderableListView` to the  
   upcoming lane in `today_screen.dart` calling `PATCH /tasks/reorder`.

**Acceptance criteria:**
- New test file passes in CI (`pytest -q`).
- Multi-task voice test ("meeting at 3, gym at 6") creates two tasks correctly.
- Dedup prevents duplicate on double-confirm.

---

## Phase 4 — Spotify / Music Control (Android-first)

**Goal:** Replace the current Spotify stub with a fully working OAuth connection  
and Companion-driven playback control.

**Current state:** `apps/api/app/modules/integrations/router.py` has a stub that:
- Generates an OAuth authorization URL (real).
- Stores the raw `code` as `access_token` (stub — never exchanges for real token).
- `/play-music` returns a deep link string (stub — no real Spotify API call).

**Fix plan:**

1. **API — complete OAuth token exchange (`/spotify/callback`):**  
   Exchange `code` for `access_token` + `refresh_token` via  
   `https://accounts.spotify.com/api/token`. Store both + `expires_at` in  
   `IntegrationToken`. Add `httpx` call (already in requirements).

2. **API — add token refresh helper** `_refresh_spotify_token(db, token)`:  
   Called automatically when `expires_at < now + 60s` before any Spotify API call.

3. **API — implement `/play-music` for real:**  
   Use Spotify Web API `PUT /me/player/play` with the user's active device.  
   Support `query` (search → play top result) and `playlist_id` (direct URI).  
   Scope required: `user-modify-playback-state user-read-playback-state streaming`.

4. **API — add `/integrations/spotify/status` endpoint:**  
   Returns `{connected: bool, display_name: str | None}` for settings UI.

5. **API — add Spotify intent to plan extractor:**  
   Extend `plan_extractor.py` to recognise music intents:  
   `"play some jazz"`, `"put on focus music"`, `"pause the music"`, `"skip this song"`.  
   New intent type `"music_control"` with field `action: play|pause|skip|query`.  
   Route through `action_executor.py`.

6. **Mobile — settings screen — "Connect Spotify" button:**  
   In `settings_screen.dart`, add an integration card that:
   - Shows "Connect Spotify" if not connected.
   - Launches the OAuth URL in an in-app WebView (`url_launcher`).
   - On redirect back to `aipal://spotify-callback`, extracts `code` + `state`  
     and POSTs to `/integrations/spotify/callback`.
   - Shows "Connected as [display_name]" + "Disconnect" if connected.

7. **Mobile — Companion plays music on intent:**  
   In `app_state.dart`, after a voice/text turn returns `tool_actions` containing  
   `"Music: playing ..."`, show a mini music chip on the Companion screen.

8. **VM — add `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` to `.env` and  
   Ansible `aipal.env.j2` template.**

9. **Fallback:** If Spotify is not connected or playback fails, Companion replies:  
   "I'd need Spotify connected to play music — go to Settings > Integrations to link it."

**Acceptance criteria:**
- User can connect Spotify in Settings without leaving the app.
- Voice command "play some focus music" starts Spotify playback on Android.
- Token refresh works silently after 1-hour expiry.
- Disconnect clears the `IntegrationToken` row.

---

## Phase 5 — Weekly Activity Email Summary

**Goal:** Each user receives (or can request) a concise weekly summary of their  
AiPal activity — tasks completed, streaks, notable patterns — delivered by email.

### Phase 5-A: Manual preview and send (MVP)

1. **API — `GET /daily/weekly-summary`** — returns a structured `WeeklySummaryResponse`:
   - `week_start`, `week_end` (user-local Monday–Sunday).
   - `tasks_completed: int`, `tasks_deferred: int`, `streak_days: int`.
   - `top_categories: list[{category, count}]`.
   - `companion_note: str` — one LLM-generated sentence summarising the week warmly.
   - `email_html: str` — pre-rendered HTML suitable for email.

2. **API — `POST /daily/weekly-summary/send`** — triggers immediate send to user's  
   registered email. Returns `{sent: bool, email: str}`.

3. **Email provider — use `resend.com` (free tier: 3K emails/month):**  
   Add `resend>=2.0` to `requirements.txt`. Add `RESEND_API_KEY` to config.  
   Sender domain: configure SPF/DKIM for `aipal.io` or use Resend's shared domain  
   during MVP. Alternative if Resend is unavailable: `sendgrid-python` (100/day free).

4. **Email template** — HTML file at `apps/api/app/templates/weekly_summary.html`  
   using Jinja2. Matches AiPal brand (dark background optional; email-safe fallback  
   light mode). Must pass Gmail, Outlook, Apple Mail rendering.

5. **Mobile — Settings — "Email weekly summary" toggle + "Send now" button:**  
   In `settings_screen.dart`, show a card under Profile with the toggle and  
   "Preview & Send" button that calls `GET /weekly-summary` then shows a bottom  
   sheet with the rendered summary before confirming send.

### Phase 5-B: Scheduled automatic send

6. **API — `POST /jobs/enqueue-weekly-summaries`** (internal/admin endpoint):  
   Queries all users with `weekly_summary_enabled=True` and enqueues a  
   `weekly_summary_email` job for each, scheduled for Sunday 8 PM user-local time.

7. **Worker — add `weekly_summary_email` job handler** in  
   `apps/api/app/modules/jobs/service.py` `HANDLERS` dict and `run_job()`.

8. **VM — cron trigger** in Ansible `aipal.env.j2`/systemd timer:  
   Every Sunday at 20:00 UTC (adjust for majority timezone offset), call  
   `POST /jobs/enqueue-weekly-summaries` internally.

9. **User model — add `weekly_summary_enabled: bool = False`** and  
   `weekly_summary_day: int = 6` (Sunday). Add Alembic migration.

**Acceptance criteria (Phase 5-A):**
- `GET /weekly-summary` returns valid data for a test account.
- "Send now" delivers the email within 10 seconds.
- Email renders correctly in Gmail and Apple Mail.

**Acceptance criteria (Phase 5-B):**
- Worker processes `weekly_summary_email` job and sends email.
- Cron fires without error; logs confirm per-user jobs enqueued.

---

## Phase 6 — Subscriber Authentication Gateway

*This phase implements the auth gateway designed in Phase 0-C.*  
Phase 0-C is the design and migration; Phase 6 is the full production rollout  
including subscriber tier enforcement.

1. **Deploy `GOOGLE_CLIENT_ID` to VM** — add to `.env` and Ansible template.
2. **Deploy Apple Sign-In credentials** — Service ID, key ID, private key to `.secrets/`.
3. **Update onboarding screen** with final Google/Apple buttons (UI polish pass).
4. **Enforce subscription tier gate** on Spotify and weekly email endpoints using  
   `require_subscription` FastAPI dependency.  
   Free tier: Today + Companion voice. Premium tier: Spotify + weekly email.
5. **Add subscription management UI stub** in Settings for future payment integration.

---

## Phase 7 — Continuous Documentation Synchronisation

After every phase and every significant fix, update:

| Document | What to update |
|----------|----------------|
| `docs/PRODUCT.md` | Phase status table, shipped features list, backlog |
| `docs/DELIVERABLES.md` | Requirement matrix (R/L/T/DLY/INT), ops items |
| `docs/stakeholder/ROADMAP.md` | Phase milestone table, competitive snapshot |
| `docs/releases/VOICE_BASELINE.md` | Gate pass/fail per build |
| `apps/mobile/pubspec.yaml` | Version bump before every Play build |
| Release snapshot in `docs/releases/done/` | After each Play Internal upload |

**Rule:** No phase is considered done until its documentation is committed and  
`docs/PRODUCT.md` reflects the new status.

---

## Execution checklist (summary)

```
[Phase 0-A] LLM streaming + latency reduction
[Phase 0-B] Date staleness bug (client refresh + server overdue lane)
[Phase 0-C] Google + Apple sign-in foundation (migration, endpoints, mobile UI)
[Phase 1 ] Voice reliability — all 7 VOICE_BASELINE gates pass
[Phase 2 ] Wake phrase model v0.2 (Hi Pal, HiPal, AiPal)
[Phase 3 ] Today intelligence uplift + regression suite
[Phase 4 ] Spotify OAuth + playback control (Android-first)
[Phase 5-A] Weekly email summary — manual preview + send
[Phase 5-B] Weekly email summary — automated scheduled send
[Phase 6 ] Subscriber gateway + tier enforcement
[Phase 7 ] Ongoing doc sync at every phase boundary
```

---

## Non-negotiable guardrails (apply to every phase)

1. **Confirm-before-commit** — no AI action silently mutates user data.
2. **Voice baseline gate** — phases 2+ must not regress gates 1–7.
3. **Secrets never committed** — all credentials in `.env` / Ansible vault.
4. **Tests before deploy** — `pytest -q` and `flutter analyze` pass before  
   every Play Internal upload.
5. **Doc-first done** — a phase is only done when documentation reflects it.
