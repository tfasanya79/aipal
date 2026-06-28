# ADR: Phase C5 — Personal Assistant Brain (Actions Over Words)

**Status:** Accepted  
**Date:** 2026-06-22

## Context

C4 shipped honest **create** flows (plan draft, confirm recovery, anti-lie guard for "added/scheduled"). Users could still ask to **reschedule** tasks by voice or text; the LLM replied "now set for 8:00 PM" while `update_task` was never called. Task edits existed only via mobile UI (`PATCH /tasks/{id}`). Docs and tester skills incorrectly implied conversational reschedule worked.

## Decision

Replace the LLM-first, create-only pipeline with a **grounded action loop**:

1. **`action_executor`** — mutations (create, update, complete, delete) execute and verify against `today_view` before the assistant claims success.
2. **`edit_task` intent** — `plan_extractor` returns `edits[]` with `match_title`, `new_due_at`, optional duration/title.
3. **`task_resolver`** — fuzzy match utterances to open Today tasks (by id/title).
4. **Hybrid confirm** — explicit reschedule → instant apply; ambiguous → edit draft + one confirm offer; `yes` → `update_task`.
5. **Universal honesty guard** — `reply_claims_mutation` covers update/complete/delete claims; post-LLM recovery or honest fallback.
6. **Schedule context** — `format_today_schedule_block` includes task `id=` and local times; LLM instructed not to invent schedule.

## Architecture

```
User turn → intent + extraction → resolve against Today
  → clear? → action_executor.apply → verify today_view → deterministic reply
  → ambiguous? → edit draft + confirm offer
  → query only? → enrich context → llm_chat → honesty guard
```

**Principles:** Today is ground truth; tool_action prefixes prove mutations; LLM narrates only.

## C4.1 clarification

C4.1 shipped **UI-only** task time/duration edit (`PATCH /tasks/{id}` from Today sheet). **Conversational** edit/reschedule is C5.

## Out of scope (C5.1+)

- OAuth calendar two-way write
- Full-duplex Live v2 (C6)
- Clinical/therapy features
- Proactive companion initiative beyond C3b nudges

## Consequences

- Play build **2.6.0+48** ships C5 (API brain; mobile 2.5.9+ UI sufficient).
- Voice freeze unchanged — STT/TTS/wake paths not modified.
- Tests: `tests/test_action_executor.py` + regression on `test_voice_booking.py`.

## References

- [`action_executor.py`](../../apps/api/app/modules/brain/action_executor.py)
- [`companion-c4.md`](./companion-c4.md) — C4.3 honesty guard (create-only)
- [`PRODUCT.md`](../PRODUCT.md) — verification scenarios
