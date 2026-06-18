# ADR: Live Voice v2 — full-duplex WebSocket

**Status:** Paused (2026-06-18)  
**Supersedes:** Accepted 2026-06-16  
**Production path:** Half-duplex v1 — `POST /turn/audio` + AAC segments (build 2.5.0+38)

## Why paused

Full-duplex v2 shipped in builds 35–37 but failed device QA: greeting TTS worked, then Live went deaf; wake word did not enter Live. Client VAD (`getAmplitude()` / PCM stream) was unreliable on the primary test device.

Recovery: hard reset mobile voice to pre-v2 half-duplex (`f3eea7d` / 2.4.1+19) plus splash boot fix only. v2 code may remain in repo on `main` but is **not** on the Live runtime path for build 38.

## Original decision (historical)

Replace batch REST Live audio with full-duplex WebSocket Live Voice v2:

| Layer | v1 (half-duplex, production) | v2 (paused) |
|-------|------------------------------|-------------|
| Transport | HTTP multipart upload | Duplex `/ws/session` |
| STT | Batch faster-whisper on file | Streaming Whisper on VM |
| LLM | Non-streaming calls | Streaming DeepSeek |
| TTS | Full MP3 in JSON | Sentence-chunked edge-tts over WS |
| Mic | Paused during playback | Continuous PCM while assistant speaks |

## Resuming v2 (future)

Only after half-duplex passes acceptance on the same hardware, or after a guaranteed fallback (e.g. push-to-talk) ships. Do not re-enable `LIVE_VOICE_V2` by default without a new ADR revision.

## Related

- [`CORE_PILLARS.md`](../CORE_PILLARS.md)
- [`releases/HALF_DUPLEX_RECOVERY.md`](../releases/HALF_DUPLEX_RECOVERY.md)
