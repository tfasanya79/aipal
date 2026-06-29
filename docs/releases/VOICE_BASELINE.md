# Voice + wake freeze

**VOICE_WAKE_FROZEN:** `partial` — targeted unfreeze through build **2.6.11+61** (2026-06-27)

See also targeted unfreeze history in this file. Frozen path list: [`.github/VOICE_WAKE_FROZEN.md`](../../.github/VOICE_WAKE_FROZEN.md).

Rollback build **2.5.4+42** restored mobile voice/wake to the **2.5.0+38** known-good path. Build 41 regressions triggered the original freeze.

## Targeted unfreeze (2.6.10–2.6.11 — Hi Pal + phantom speech)

| Change | Files |
|--------|-------|
| Mic warmup 3s — block startup false wake | `wake_word_engine.dart` |
| Wake suppress: block fire only, not mic start; re-sync after expiry | `app_state.dart` |
| Lifecycle-gated foreground route (no FGS while resumed) | `app_state.dart`, `main.dart` |
| Orb force-end: stop TTS, clear in-flight turn | `app_state.dart` |
| API: single-word STT discard, media ambient patterns, suppress `_HONEST_NOT_ADDED` on non-booking voice | `router.py` |

## Targeted unfreeze (2.6.3+51 — post-C5.2 QA fixes)

| Change | Files |
|--------|-------|
| Wake from Resting: suppress FGS before Live mic; `ensure_listening` ping on resume/sync | `app_state.dart`, `wake_*`, `main.dart` |
| Ambient STT hallucination discard (therapy-style false transcripts) | `router.py` |
| Audio turn timeout 45 s; friendly recovery; end session after 2 timeouts | `api_client.dart`, `app_state.dart` |
| Tomorrow booking date shift + auto-confirm day guard | `plan_extractor.py`, `plan_intent.py`, `router.py` |

## Targeted unfreeze (2.6.2+50 — C5.2 conversation session)

User-approved fixes for post-C5 voice UX:

| Change | Files |
|--------|-------|
| Bounded conversation session (multi-turn + 18 s idle timeout) | `app_state.dart`, `companion_screen.dart` |
| Greeting TTS before VAD start; mic suppressed during greeting/speech | `app_state.dart` |
| Discarded segments stay in session; soft prompt after 2 rejects | `live_voice_loop_io.dart`, `app_state.dart` |
| Wake lifecycle: 800 ms FGS restart, `engine_ready` timeout/retry, zombie recovery | `app_state.dart`, `wake_foreground_handler.dart` |
| Noise gating (min voiced duration, skip empty STT TTS) | `live_voice_loop_io.dart`, `router.py` |

**Still forbidden:** C6 full-duplex, `LIVE_VOICE_V2`, PCM streaming experiments, sensitivity slider.

## Live mode behavior (2.6.2+)

- **Resting** default — mic loop off; wake word active when enabled
- **Conversation session** — orb tap or "Hi Pal" → optional greeting → listen → reply → **listen again** for follow-ups
- **End session** — 18 s silence, "bye" / "that's all", or orb tap → Resting; wake resumes
- **Task nudges** (~12 min before due) speak TTS while Resting only; do not reopen mic loop
- Empty/noise STT: silent discard (`skip_tts`), no "did not catch that clearly" spam

## Device QA gates (C5.2)

| # | Scenario | Pass |
|---|----------|------|
| 1 | Hi Pal → speak → reply → 18 s silence → Resting; Hi Pal works again | Fix applied — requires device QA verification on next build |
| 2 | Hi Pal → reschedule → say **yes** in same session (if confirm offered) | |
| 3 | Tap orb → greeting plays → then mic opens → no instant Resting | Fix applied — requires device QA verification on next build |
| 4 | Ambient TV noise while Resting | Fix applied — requires device QA verification on next build |
| 5 | Tap orb → mumble too quietly | Stays Listening or soft prompt; not zombie Live |
| 6 | Orb tap during conversation | Fix applied — requires device QA verification on next build |
| 7 | Task nudge while Resting | TTS only, mic stays off |

## Code fixes applied (Phase 1 — gates 1, 3, 4, 6)

| Gate | Root cause assessed | Fix | Commit |
|------|---------------------|-----|--------|
| 1 | `_endConversation` idle-timer path re-arms wake | **Already correct** — `_restartWakeAfterLive()` → `await syncWakeListener()` is called after `_inConversation = false` (lines 879, 891, 925 in `app_state.dart`). No code change needed; gate requires device QA. | TBD |
| 3 | Mic must not open until greeting TTS finishes | **Already correct** — `_awaitingGreeting = true` before `_playLiveGreeting()`, reset to `false` after; `loop.start()` (mic open) only called after greeting completes (lines 827–833 in `app_state.dart`). No code change needed; gate requires device QA. | TBD |
| 4 | STT picks up ambient TV/video audio while Resting | Extended `_MEDIA_AMBIENT` regex in `apps/api/app/modules/voice/router.py` with common broadcast/YouTube phrases: `subscribe and hit the bell`, `like and subscribe`, `smash that like`, `stay tuned`, `back with another`, `welcome back to`, `previously on`, `coming up next`, `after the break`, `new episode`, `season finale`, `breaking news`, `brought to you by`, `tonight on`, `this week on`. | TBD |
| 6 | Double-tap orb could leave `_inConversation` in wrong state | **Already correct** — `_toggleLiveInProgress` flag with `try/finally` guard already present in `toggleLive()` (lines 760–780 in `app_state.dart`). No code change needed; gate requires device QA. | TBD |

Smoke script added: `scripts/voice-gate-smoke.sh` — tests `/health`, `POST /turn/text`, `GET /turn/greeting`, `GET /today` against local API.

## Baseline reference

| Field | Value |
|-------|--------|
| Original known good | `2.5.0+38` |
| C5 brain | `2.6.0+48` |
| One-shot Live hotfix | `2.6.1+49` |
| Conversation session | `2.6.2+50` |
| Trust / wake / booking hotfix | `2.6.4+52` |
| Post-C5.2 QA fixes | `2.6.3+51` |
| Voice reliability hotfixes | `2.6.10+60` – `2.6.11+61` |
| Architecture | Half-duplex AAC → `POST /turn/audio` |

See also [`HALF_DUPLEX_RECOVERY.md`](HALF_DUPLEX_RECOVERY.md), [`../decisions/live-voice-v2.md`](../decisions/live-voice-v2.md).

## Wake model v0.2 (deferred)

`hi_pal_v0.2.onnx` retrain with real speaker clips is **deferred** until device QA gate #5 (Hi Pal reliability) fails on build 50. See [`../decisions/wake-word-engine.md`](../decisions/wake-word-engine.md).
