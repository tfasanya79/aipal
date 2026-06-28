---
name: aipal-testers
description: >-
  Post-deploy tester brief for AiPal Play Internal / web stakeholders. Use after
  deploy-all.sh or when user asks for tester instructions, QA handoff, or beta
  release notes for humans.
---

# AiPal tester brief

Use this skill **after a deploy** to produce a short brief for human testers (Play Internal, sideload APK, or web `/app/`).

**Scope:** post-deploy human verification only. Pre-ship automated gates (pytest, `flutter test`, smoke) live in `release-qa-agent`.

## When to use

- `./scripts/deploy-all.sh` completed successfully
- User says "tester brief", "what should testers check", or "Play release notes"
- Handoff from `release-qa-agent` manual checklist to stakeholders

## Template (fill and send)

```markdown
# AiPal tester brief — [VERSION] — [DATE]

**Build:** [e.g. 2.6.3+51]  
**Install:** Play Internal opt-in link OR [APK URL] OR https://[host]/app/

## What changed
- **Post-C5.2 hotfix (2.6.3):** wake mic handoff before Live, ambient STT discard (no therapy spam in quiet room), 45s voice timeout with recovery, tomorrow booking date + honesty guards
- **Conversation session:** tap orb or say Hi Pal → optional greeting → speak → hear reply → **stay listening** for follow-ups ("yes", "what about tomorrow?")
- Session ends after **18 s silence**, saying **bye**, or **tap orb again** → Resting; Hi Pal works again
- Greeting plays **before** mic opens (no more greeting eating your first sentence)
- Clear reschedule ("move Sweden Open to 8pm") still updates instantly without "say yes"

## Priority retest (reported bugs — must pass)

1. **Hi Pal from Resting** — enable wake → leave Companion on Resting → say "Hi Pal" (no orb) → Live starts.
2. **Quiet room** — Resting near silence/TV 2 min → no unsolicited emotional replies.
3. **Slow turn** — normal question → no raw TimeoutException; if slow, friendly message or clean Resting after 2 failures.
4. **Tomorrow booking** — "book a team meeting tomorrow at 8am" → task on **Tomorrow** in Today (not Today-only lie).

## Please test (15 min)

1. **Onboarding** — clear app data → email screen stays until valid email + Continue → profile completes without crash.
2. **Login** — email dev flow; confirm name on Companion.
3. **Conversation session** — tap orb → greeting (if any) → speak → reply → chip stays **Live — listening** → say a follow-up → second reply works.
4. **Idle timeout** — after a reply, wait **18+ seconds** silent → chip shows **Resting** → say Hi Pal again → new session works.
5. **End session** — during Live, tap orb → Resting immediately → Hi Pal works without toggling Settings.
6. **Ambient silence** — stay on Companion Resting near noise/TV → should **not** start Live or spam replies.
7. **Hi Pal wake** — enable in Settings → say "Hi Pal" while Resting → conversation session → follow-up works → idle or bye → Resting.
8. **Reschedule (C5)** — add task at 7pm → "move [task] to 8pm" → instant update, no confirm.
9. **Vague reschedule** — "change it to 8" → confirm offer → say **yes** in same session → updates.
10. **Nudge** — add task due in ~15 min → ~12 min before, notification + spoken nudge on Companion if app open (mic stays off).
11. **Today** — priority lanes, suggest routines, focus timer; tap task to edit time/duration in sheet.
12. **Settings** — build number matches [VERSION]; wake errors shown if permissions block Hi Pal.
13. **Background wake (Android)** — enable "Listen for Hi Pal" → confirm listening notification → switch to Today or home screen → say "Hi Pal" → app opens and goes Live.

## Known limits
- Voice reschedule/edit via chat — **C5 shipped**; OAuth calendar two-way write still deferred.
- Wake word **Hi Pal** (Android): Settings opt-in; ongoing notification while listening; swipe-kill stops service.
- Wake model v0.2 retrain deferred until device QA shows Hi Pal still unreliable on build 50.
- iOS: Companion tab only while app is open.
- Full-duplex Live v2 (C6) paused — production uses half-duplex `POST /turn/audio`.
- iOS TestFlight: [status or N/A].

## Report issues
- Screenshot + steps + device/OS
- Tag: brain / today / voice / crash
```

## Rules

- App name is **AiPal** only in tester-facing copy.
- Do not name third-party planner apps in briefs.
- Do not promise "move swim to 7" via follow-up unless C5 edit path is in the build under test.
- Point testers at `docs/PRODUCT.md` verification table and `docs/releases/VOICE_BASELINE.md` device QA gates for expected behavior.
