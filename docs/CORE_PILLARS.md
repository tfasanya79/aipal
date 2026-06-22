# AiPal core pillars

Non-negotiable product capabilities. Feature work pauses until acceptance passes on the current Play Internal build.

| Pillar | Acceptance (one device test) |
|--------|------------------------------|
| **Live voice** | Tap orb → greeting → speak → spoken reply | **PASS** (build 38, 2026-06-18) |
| **Wake word** | Resting → "Hi Pal" → enters Live | **PASS** (build 38) |
| **Companion brain** | Multi-turn context, mem0 memory, mood-aware tone, device calendar context, evening reflection; plan drafts + Today |

## Live voice — production architecture (2026-06-18)

**Half-duplex (v1)** is production and **baseline-locked**. Build **2.5.0+38** passed device QA on 2026-06-18. See [`releases/VOICE_BASELINE.md`](releases/VOICE_BASELINE.md).

- `LiveVoiceLoop` records AAC segments, uploads via `POST /turn/audio`
- Mic pauses during TTS playback (turn-taking)
- Non-streaming latency accepted for baseline
- No full-duplex WebSocket streaming on the Live path

**Live Voice v2** (full-duplex PCM over `/ws/session`) is **paused** until half-duplex passes device QA. See [`decisions/live-voice-v2.md`](decisions/live-voice-v2.md).

## Stop rule

Voice baseline **passed** on build 38. Further voice architecture changes require explicit ADR revision and device QA. See [`releases/VOICE_BASELINE.md`](releases/VOICE_BASELINE.md).
