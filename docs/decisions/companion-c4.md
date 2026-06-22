# ADR: Phase C4 — Companion depth

**Status:** Accepted  
**Date:** 2026-06-20

## Context

Contributor feedback: shipped QA and architecture skew **planner** (tasks, plans, nudges) over **companion** (memory, emotion, continuity, reflection). C4 adds companion **foundation** without replacing Today as operational memory or violating voice freeze / non-clinical positioning.

## Contributor alignment

| Pillar | C4 delivery | Deferred (C5+) |
|--------|-------------|----------------|
| Memory | mem0 every turn + structured metadata | Episodic summaries, snooze-pattern learning |
| Context continuity | `context_builder`: history + mem0 + calendar + profile | Cross-session “last time we talked about…” UI |
| Emotion | VADER tone hints → prompt adaptation only | Clinical/diagnostic paths (rejected) |
| Reflection | Evening/morning `companion_line` + review sheet | Weekly reflection ritual |
| Calendar | Light device calendar → brain context | OAuth sync, two-way write-back |
| Initiative | Existing C3b task nudges unchanged | Companion check-ins after events |
| Personal growth | — | User goals model, progress narratives |
| Relationship building | mem0 + personalized copy + reflection | Explicit relationship rituals |

## Decision

1. **Brain pipeline:** `Memory + Context + Mood → Plan tools → Response` via [`context_builder.py`](../../apps/api/app/modules/brain/context_builder.py).
2. **Today** remains operational memory; **mem0** is relational memory.
3. **Calendar:** read-only from phone OS calendars (`device_calendar` → `calendar_events_cache`), not OAuth micro-sync.
4. **Mood:** non-clinical tone bands (`gentle` / `neutral` / `upbeat`) only — never diagnosis.
5. **Voice freeze:** no changes to STT/TTS control flow or frozen mobile wake/live paths.

## C5 preview (not in C4)

- Goals layer in profile → `context_builder`
- Companion initiative (opt-in check-ins)
- Weekly reflection ritual
- “Remember when…” surfacing in Companion tab

## Consequences

- `MEM0_ENABLED=true` required in production env for full C4 benefit.
- Device calendar permission required on mobile for calendar-aware replies.
- Play build **2.5.6+44** ships C4 mobile hooks (calendar sync on Today/resume, review UI).
