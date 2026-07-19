# AGENTS.md — Standing rules for any agent (human or AI) working on this repo

These rules are load-bearing. They exist because violating them has directly caused
wasted money, shipped regressions, or repeated debugging loops in past rounds. Follow
them even if a specific task description doesn't repeat them.

## 1. VM-first development — NO LOCAL DEVELOPMENT

All code changes, builds, tests, commits, and deploys for this project MUST happen via
SSH on the project VM, never on a local machine. The local machine (if any) is
read-only, for reference/browsing only.

- Edit code: SSH in, edit files in `~/aipal` on the VM.
- Run tests: SSH in, run `pytest` (API) / `flutter test` (mobile) in `~/aipal`.
- Commit: SSH in, `git commit` in `~/aipal`.
- Build: SSH in, `flutter build` / gradle in `~/aipal`.
- Deploy: SSH in, run `scripts/deploy-android-internal.sh` (or `deploy-all.sh`) in `~/aipal`.
- Push: SSH in, `git push origin main` from `~/aipal`.

Why: prevents split state between local and VM code, ensures Play builds use tested
VM code, eliminates "forgot to push" / "built from stale code" classes of bugs.

## 2. Evidence-based changes only — no speculative "gambling" fixes

Every change must be justified by something you actually read/observed: source code,
logs (`journalctl -u aipal-v2`), test output, or a reproduced symptom — not a guess.
If you're not sure a change fixes the reported symptom, say so explicitly and ask
before shipping, rather than shipping speculatively and waiting to see if it worked.
Each deployed build costs the user real money/time to test on-device — treat that
cost as real.

## 3. Always update todo status immediately when work is done

Whenever a task/todo is completed, mark it `done` in the same turn you finish it —
with the same non-negotiable discipline already applied to updating `docs/PRODUCT.md`.
Stale todos that were actually completed in an earlier round have repeatedly caused
wasted re-investigation and risk of redundant rework. Before starting new work on an
old backlog item, re-verify against the actual current code — the tracker has been
found stale multiple times.

## 4. Keep `docs/PRODUCT.md` current

Every shipped round should get a dated section in `docs/PRODUCT.md` describing what
changed and why (root cause for bug fixes, not just symptom).

## 5. Wake-word / voice-pipeline changes need extra care

The wake-word engine and voice state machine (`services/voice/*`,
`wake_foreground_handler.dart`, `wake_background_service_io.dart`,
`live_voice_loop_io.dart`, `app_state.dart`) have a long history of subtle,
hard-to-reproduce bugs (isolate crashes, stale service state, mic ownership races).
Changes here should be small, individually testable, and validated with
`flutter analyze` + `flutter test` before every deploy. Don't refactor broad swaths
of this area in one shot.

## 6. Backend service name

The production API systemd service is `aipal-v2` (not `aipal-api`). Use
`sudo journalctl -u aipal-v2 --since '...' --no-pager` for backend logs. Backend
code lives at `/opt/aipal-v2` on the VM (deployed copy, separate from `~/aipal`
the git checkout).

## 7. SSH access

```
ssh aipal-vm
```
(Configured in `~/.ssh/config`: HostName=43.160.220.9, User=dev,
IdentityFile=~/.ssh/aipal_copilot_ed25519)
