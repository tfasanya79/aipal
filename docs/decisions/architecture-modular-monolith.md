# ADR: Modular monolith (not microservices)

**Status:** Accepted  
**Date:** 2026-06-18

## Context

AiPal runs as a single API process on one Tencent VM with one Postgres database and one Flutter mobile app. Contributor feedback correctly identified monolithic coupling (fat `AppState`, mixed routers, `create_all` without migrations, in-memory OAuth state, no job queue). A blind split into microservices would add latency, ops burden, and failure modes inappropriate for a 1–3 person team and half-duplex voice.

## Decision

Evolve AiPal as a **modular monolith**:

| Module | Responsibility |
|--------|----------------|
| `auth` | Magic link, JWT, profile |
| `brain` | LLM, conversation, plan extraction, memory, safety |
| `voice` | STT/TTS, audio turn, WebSocket session (**FROZEN** surface while `VOICE_WAKE_FROZEN`) |
| `today` | Tasks, today view, suggest-day, plan drafts |
| `integrations` | OAuth tokens, calendar cache |
| `jobs` | Postgres-backed async work (same VM worker) |
| `shared` | DB, config, schemas, models |

**In-process boundaries:** modules communicate through explicit service functions and shared schemas — no cross-import of router internals.

**Deploy unit:** one API (`uvicorn`), one worker (`aipal-worker.service`), one mobile binary. Not separate microservices.

## Consequences

- Voice turn latency stays in-process (STT → brain → TTS).
- Schema changes go through Alembic; `create_all` remains for dev/test bootstrap.
- Extract a service to its own deployable **only** when independent scale or release cadence justifies it (e.g. dedicated STT farm at high concurrency).

## Alternatives rejected

- **Microservices now:** network hops hurt voice; ops cost exceeds team capacity.
- **Big-bang rewrite:** risk during voice freeze; phased extraction preferred.

## References

- [`docs/releases/VOICE_BASELINE.md`](../releases/VOICE_BASELINE.md)
- [`.github/VOICE_WAKE_FROZEN.md`](../../.github/VOICE_WAKE_FROZEN.md)
