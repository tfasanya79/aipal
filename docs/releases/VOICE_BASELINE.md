# Voice + wake freeze

**VOICE_WAKE_FROZEN:** `true` (since 2026-06-18)

Rollback build **2.5.4+42** restores mobile voice/wake to the **2.5.0+38** known-good path. Build 41 regressions triggered this freeze.

**Freeze ≠ disable:** Half-duplex Live voice and wake-word ("Hi Pal") remain **fully enabled** and must behave identically to build 38. The freeze only blocks **code changes** to voice/wake paths — not product functionality.

## Allowed while frozen

- Docs, Today UI, brain/prompts, schema migrations, infra, modular-monolith refactor
- Text chat and plan-draft flows
- Session export for **text** turns only (no logger on live/wake hot path)

## Forbidden until explicit unfreeze

- `apps/mobile/lib/providers/app_state.dart` — `toggleLive`, `_handleVoiceSegment`, `syncWakeListener`, `_syncAndroidBackgroundWake`, wake handlers
- `apps/mobile/lib/services/live_voice_loop_io.dart`
- `apps/mobile/lib/services/wake_*.dart` (behavior changes)
- `LIVE_VOICE_V2` / `liveVoiceV2` / `LiveVoiceSession` / `voice_turn.py` runtime enablement
- Any VAD threshold, PCM, or full-duplex experiments

## Unfreeze process

1. User says **unfreeze** in writing
2. One hypothesis per Play build
3. Device QA pass on same hardware before merging

## Baseline reference

| Field | Value |
|-------|--------|
| Last known good | `2.5.0+38` |
| Rollback ship | `2.5.4+42` (voice-identical to 38) |
| Code anchor | `f3eea7d` + splash boot fix |
| Architecture | Half-duplex AAC → `POST /turn/audio` |

See also [`HALF_DUPLEX_RECOVERY.md`](HALF_DUPLEX_RECOVERY.md), [`../decisions/live-voice-v2.md`](../decisions/live-voice-v2.md).
