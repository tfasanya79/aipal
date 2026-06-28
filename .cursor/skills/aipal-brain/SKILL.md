---
name: aipal-brain
description: >-
  AiPal C5 Personal Assistant brain: action_executor, edit_task intent, hybrid
  confirm, universal honesty guard. Mutations execute before LLM claims success.
  Use when editing turn/text, plan drafts, task edits, or testing reschedule flows.
---

# AiPal Brain (C5 — Actions Over Words)

## Turn pipeline

```
POST /turn/text  { text, session_id? }
  → load conversation_turns + plan_draft (create or edit)
  → today_view snapshot (ground truth)
  → confirm/discard early exit (create draft OR edit draft)
  → confirm recovery (yes after offer, no draft) → action_executor
  → apply_task_tools_from_text (list/complete regex)
  → plan_extractor (plan_day | edit_task | complete_task | check_in | other)
  → action_executor.try_handle_edit_extraction (instant or offer confirm)
  → action_executor.try_handle_delete
  → save plan_draft for new bookings (never auto-create except voice auto-book)
  → llm_chat (prose only — narrates, does not mutate)
  → universal honesty guard (reply_claims_mutation vs tool_actions)
  → append turns; return { reply, session_id, tool_actions, plan_draft? }
```

Key files:
- `apps/api/app/modules/voice/router.py` — `_reply_for_text` (shim: `app.routers.turn`)
- `apps/api/app/modules/brain/action_executor.py` — grounded create/update/complete/delete
- `apps/api/app/modules/brain/task_resolver.py` — fuzzy match user text → Today task id
- `apps/api/app/modules/brain/plan_extractor.py` — LLM JSON incl. `edit_task` + `edits[]`
- `apps/api/app/modules/brain/plan_intent.py` — confirm/edit/clear-edit + honesty guard
- `apps/api/app/modules/brain/context_builder.py` — schedule block with `id=` + local times
- `apps/api/app/modules/today/plan_draft.py` — draft persistence (create + edit payloads)
- `apps/api/app/modules/today/tasks.py` — `create_task`, `update_task`, `today_view`

## Mutation rules (C5)

1. **Today + schedule block = ground truth** — LLM must not invent times; tasks listed with `id=` and local wall clock.
2. **Every mutation claim needs a tool action** — prefixes: `Confirmed plan:`, `Updated task:`, `Completed:`, `Deleted task:`.
3. **LLM narrates; executor mutates** — chat text alone never changes the DB.
4. **Hybrid edit confirm** — clear request (`move Sweden Open to 8pm`) → instant `update_task`; vague (`change it to 8`) → edit draft + offer; `yes` → apply.
5. **Never silently create tasks** — new plans go to `plan_drafts`; user confirms (or voice auto-book when explicit book + time + duration).
6. **Always use `session_id`** — reuse across turns; load history before LLM.
7. **User-local today** — `timezone_util.user_local_today`; schedule times in user TZ.

## Edit intent shape

```json
{
  "intent": "edit_task",
  "edits": [{
    "match_title": "Sweden Open",
    "new_due_at": "2026-06-22T20:00:00+02:00",
    "new_estimated_minutes": null
  }],
  "clarifying_question": null
}
```

## Honesty guard

`plan_intent.reply_claims_mutation(reply)` catches add **and** update/complete/delete claims (`set for`, `moved`, `updated`, etc.). Post-LLM in router: if claim without matching tool_action → attempt edit/add recovery or honest fallback (*"I haven't changed anything on Today yet."*).

## Test scenarios

Run: `cd apps/api && pytest tests/test_action_executor.py tests/test_voice_booking.py tests/test_plan_timezone.py -q`

| Scenario | Input | Expected |
|----------|-------|----------|
| Reschedule instant | `"move Sweden Open to 8pm"` | `Updated task:` + Today `due_at` changes |
| Reschedule confirm | `"change it to 8"` → `"yes"` | Offer first; then `Updated task:` |
| False update lie | LLM says "set for 8pm" with no tool | Guard rewrites or recovers |
| Voice book | `"book 6pm appointment 30 min"` | Auto-confirm single task |
| Confirm recovery | Assistant offered add, user `yes`, no draft | `Confirmed plan:` + real create |

Mock `plan_extractor.extract_plan` and `llm_chat` in integration tests; unit-test `action_executor` directly.

## Mobile

- `PlanDraftCard` — confirm create drafts (edit confirm is voice/text "yes")
- Today task edit sheet — `PATCH /tasks/{id}` (UI path; voice uses action_executor)
- `apps/mobile/lib/providers/app_state.dart` — `sendTextTurn`, refresh Today after voice

## Voice freeze

C5 is brain/router only. Do **not** change STT/TTS/wake/`live_voice_loop_io.dart` unless explicitly unfreezing voice.
