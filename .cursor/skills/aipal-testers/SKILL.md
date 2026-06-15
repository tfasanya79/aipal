---
name: aipal-testers
description: >-
  Post-deploy tester brief for AiPal Play Internal / web stakeholders. Use after
  deploy-all.sh or when user asks for tester instructions, QA handoff, or beta
  release notes for humans.
---

# AiPal tester brief

Use this skill **after a deploy** to produce a short brief for human testers (Play Internal, sideload APK, or web `/app/`).

## When to use

- `./scripts/deploy-all.sh` completed successfully
- User says "tester brief", "what should testers check", or "Play release notes"
- Handoff from `release-qa-agent` manual checklist to stakeholders

## Template (fill and send)

```markdown
# AiPal tester brief — [VERSION] — [DATE]

**Build:** [e.g. 2.1.2+13]  
**Install:** Play Internal opt-in link OR [APK URL] OR https://[host]/app/

## What changed
- [1–3 bullets from PRODUCT.md or release commit]

## Please test (15 min)

1. **Login** — email dev flow; confirm name on Companion.
2. **Text plan** — "meeting at 4pm and swimming at 6pm" → confirm card → **Today** shows both with short titles and times.
3. **Voice plan** — Live: "remind me to go to bed at 8pm" → confirm card shows **Bedtime · 8:00 PM** (not a long sentence title).
4. **Follow-up** — same chat: "move swim to 7" → AiPal remembers; no re-greeting.
5. **Nudge** — add task due in ~15 min → ~12 min before, notification + spoken nudge on Companion if app open.
6. **Live** — tap orb once → speak one sentence → hear reply. Greeting should mention your day if tasks exist.
7. **Today** — priority lanes, suggest routines, focus timer on a task.
8. **Settings** — build number matches [VERSION].
9. **Background wake (Android)** — enable "Listen for Hi Pal" → confirm listening notification → switch to Today or home screen → say "Hi Pal" → app opens and goes Live.

## Known limits
- Wake word **Hi Pal** (Android): Settings opt-in; ongoing notification while listening; swipe-kill stops service.
- iOS: Companion tab only while app is open.
- iOS TestFlight: [status or N/A].

## Report issues
- Screenshot + steps + device/OS
- Tag: brain / today / voice / crash
```

## Rules

- App name is **AiPal** only in tester-facing copy.
- Do not name third-party planner apps in briefs.
- Point testers at `docs/PRODUCT.md` verification table for expected behavior.
