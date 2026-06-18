# Voice baseline (locked)

**Status:** PASS  
**Build:** `2.5.0+38` (Play Internal)  
**Tester:** Tim (`teems5uk@gmail.com`)  
**Date:** 2026-06-18  
**Branch:** `recovery/half-duplex-2.4.1`  
**Code anchor:** `f3eea7d` (2.4.1+19) + splash boot fix only

## Architecture (production)

Half-duplex Live voice:

- `LiveVoiceLoop` → AAC m4a segments → `POST /turn/audio` → STT → brain → TTS
- Mic paused during TTS playback (turn-taking)
- No `LiveVoiceSession`, no PCM WebSocket streaming, no `LIVE_VOICE_V2`

Latency is non-streaming (batch upload per utterance). Accepted for baseline.

## Acceptance criteria (passed)

| Check | Result |
|-------|--------|
| Tap orb → greeting → speak → spoken reply | PASS |
| Resting → "Hi Pal" → enters Live | PASS |

## Do not touch (without new ADR + device QA)

- `apps/mobile/lib/services/live_voice_loop_io.dart` — AAC + `getAmplitude()` VAD
- `toggleLive()` / `_handleVoiceSegment()` voice path in `app_state.dart`
- `LiveVoiceSession`, `pcm_stream_recorder`, `voice_turn.py`
- `LIVE_VOICE_V2` / `liveVoiceV2` flags
- Builds 35–37 mic-handoff / PCM VAD experiments

## Full-duplex v2

Paused. See [`../decisions/live-voice-v2.md`](../decisions/live-voice-v2.md).

## Recovery history

See [`HALF_DUPLEX_RECOVERY.md`](HALF_DUPLEX_RECOVERY.md).
