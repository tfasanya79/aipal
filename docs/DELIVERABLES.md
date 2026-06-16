# AiPal — Deliverables Tracker

**Last audited:** 2026-06-16  
**App version:** `2.4.1+19` ([`apps/mobile/pubspec.yaml`](../apps/mobile/pubspec.yaml))  
**Canonical phase detail:** [`PRODUCT.md`](PRODUCT.md)  
**Application code:** this repository  
**Extended docs hub (dev VM):** `/home/dev/docs` — architecture, backlog, `done/` snapshots (paths below)

This document is the **master audit** of what has been delivered, what remains, and what needs improvement. It synthesizes product phases, v2 requirements, ops milestones, releases, QA tooling, and documentation health. When sources disagree, this file and `PRODUCT.md` take precedence over stale backlog epics.

---

## 1. Executive summary

| Domain | Done | In progress | Deferred | Not started |
|--------|------|-------------|----------|-------------|
| **Product phases (A–C)** | 32 items | 0 | 3 | 2 |
| **Requirements (R/L/T/DLY/INT)** | 14 IDs | 0 | 0 | 8 IDs partial; 6 not started |
| **Ops & infrastructure** | 6 | 0 | 0 | 1 optional cleanup |
| **Release & distribution** | 4 | 0 | 0 | 1 (iOS TestFlight) |
| **QA & agent tooling** | 5 | 1 | 0 | 0 |
| **Documentation** | 4 | 0 | 0 | 3 stale |

**Narrative:** Phases **A** (conversational brain), **B** (brand + Today polish), and **C0–C3b** (wake word, Android background listening, smart Today logging, proactive nudges) are **shipped** on Play Internal **2.4.0+18**. Phase **C** is marked in progress in `PRODUCT.md` only because **C4** (mem0 + calendar) is deferred and the **sensitivity slider** is deferred. v2.0 core requirements (R, L, T) are largely **done**; calendar and third-party integrations are **not started**. Ops stack is **live** on the Tencent VM; iOS TestFlight and several doc artifacts need catch-up.

---

## 2. Product deliverables (phases A → C4)

Source: [`PRODUCT.md`](PRODUCT.md)

### Phase A — Conversational brain + chat-to-Today (Done)

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| A1 | `conversation_turns` + history in `turn.py` / `ws_session.py` | **Done** | Multi-turn `session_id` on text and Live WS |
| A2 | `plan_extractor.py` (LLM JSON tasks + times) | **Done** | Plan draft pipeline |
| A3 | Plan draft GET / confirm / discard + Flutter confirm flow | **Done** | `PlanDraftCard`, confirm / Not now |
| A4 | Contextual live greeting; skip generic opener if chatted today | **Done** | `/daily/live-greeting` |
| A5 | `test_brain_v11.py` + smoke plan-draft path | **Done** | pytest + `smoke-test.sh` |

### Phase B — Visible brand + Today visual polish (Done)

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| B1 | `AiPalBrandRow` on Companion + Today; onboarding orb/wordmark | **Done** | `aipal_logo.dart`, favicon cache-bust |
| B2a | Priority lanes | **Done** | `priority_lanes.dart` |
| B2b | Routine quick-add chips → plan draft | **Done** | Today routine chips |
| B2c | Focus timer circular dial | **Done** | `focus_timer_bar.dart` |
| B2d | Suggest for me → `POST /tasks/suggest-day` | **Done** | Suggest-day API + UI |

### Phase C0 — Decisions & foundations (Done)

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| C0-1 | Wake word engine decision doc | **Done** | [`decisions/wake-word-engine.md`](decisions/wake-word-engine.md) |
| C0-2 | Today snapshot in every LLM turn | **Done** | Brain context injection |
| C0-3 | Ban push-to-talk phrasing in LLM + Live greetings | **Done** | Voice UX copy rules |
| C0-4 | `today-view` default day = user timezone | **Done** | TZ-aware Today |
| C0-5 | Tester brief skill + release QA extensions | **Done** | `aipal-testers` skill, `release-qa-agent` |
| C0-6 | `aipal-brain` skill: Today as operational state | **Done** | `.cursor/skills/aipal-brain/` |

### Phase C1 — Foreground wake (Done; one deferral)

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| C1-1 | OpenWakeWord Flutter integration (`hi_pal_v0.1.onnx`) | **Done** | `open_wake_word` FFI |
| C1-2 | Wake → start Live in Companion | **Done** | `toggleLive` on wake |
| C1-3 | Settings: "Listen for Hi Pal" toggle (default off) | **Done** | Settings screen |
| C1-4 | Companion teaching copy + wake intro greeting | **Done** | `/daily/live-greeting?show_wake_intro` |
| C1-5 | Sensitivity slider | **Deferred** | Threshold tuning only; slider not shipped |

### Phase C2 — Background listening (Done — Android)

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| C2-1 | Android foreground service + notification (microphone FGS) | **Done** | `flutter_foreground_task`; Play **2.4.0+18** |
| C2-2 | Wake across tabs and when app backgrounded (screen on) | **Done** | Background wake path |
| C2-3 | Suppress listening during Live / TTS | **Done** | Live session guard |
| C2-4 | Battery note in Settings; threshold + cooldown tuning | **Done** | Sensitivity slider still deferred |
| C2-5 | iOS foreground-only on Companion tab | **Done** | Shortcuts / background iOS later |

### Phase C3a — Smart Today logging (Done)

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| C3a-1 | Remove silent regex task creation from chat turns | **Done** | Confirm-before-commit |
| C3a-2 | Plan extractor: 1–4 word titles + notes field | **Done** | Concise titles |
| C3a-3 | Dedup on plan confirm | **Done** | Today dedup logic |
| C3a-4 | Voice plan_draft on audio turn + PlanDraftCard on Companion | **Done** | Voice draft UX |
| C3a-5 | Voice/text confirm intent ("yes add to today") | **Done** | Natural confirm |

### Phase C3b — Proactive nudges (Done)

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| C3b-1 | Local notifications ~12 min before `due_at` | **Done** | Local notifications |
| C3b-2 | `GET /daily/task-nudge` dynamic message (wake_name) | **Done** | API nudge copy |
| C3b-3 | Foreground TTS on Companion when app open | **Done** | TTS nudge |
| C3b-4 | Quiet hours + daily nudge cap | **Done** | Guardrails |

### Phase C4+ — Deferred / not started

| ID | Deliverable | Status | Evidence / notes |
|----|-------------|--------|------------------|
| C4-1 | Richer mem0 retrieval every turn | **Not started** | Deferred in PRODUCT.md |
| C4-2 | Calendar import | **Not started** | Deferred; maps to T-4 |

### Verification deliverables (regression)

These scenarios from `PRODUCT.md` define **acceptance criteria** for shipped work. Re-run after major releases.

| Scenario | Expected | Last verified |
|----------|----------|---------------|
| Text: "meeting 4pm, swim 6pm" | Plan draft card; confirm → Today shows timed tasks | Manual / smoke (ongoing) |
| Voice: "remind me to go to bed at 8pm" | Draft title "Bedtime"; no task until confirm | Manual (ongoing) |
| Task due in 15 min | Notification + TTS nudge on Companion (if foreground) | Shipped C3b |
| Android: Hi Pal with app backgrounded | Notification visible; wake → Live | Shipped C2 |
| iOS: Hi Pal | Companion tab only while app open | By design |
| Follow-up same `session_id` | No re-greeting; references prior turn | Shipped A |
| Live with open tasks | Greeting mentions up next; no "tap to talk" | Shipped A/C0 |
| Today view near midnight (user TZ) | Tasks match user's local "today" | Shipped C0 |

---

## 3. Requirement matrix (R / L / T / DLY / INT)

Source: [`architecture/requirement-file-v2.md`](architecture/requirement-file-v2.md) cross-walked with implementation. **Do not** use [`backlog/`](backlog/) epics for status — those checkboxes are stale.

### R — Registration and profile

| ID | Requirement | Target | Status | Notes |
|----|-------------|--------|--------|-------|
| R-1 | First-launch onboarding creates account + profile | v2.0 | **Done** | Flutter onboarding flow |
| R-2 | Email magic link auth → JWT | v2.0 | **Done** | `POST /auth/register`, `/auth/verify` |
| R-3 | Profile: name, wake name, timezone, about-me | v2.0 | **Done** | `GET/PUT /profile` |
| R-4 | Progressive consent (mic, notifications) | v2.0 | **Partial** | Mic on Live; notification prompts exist; integration consent N/A until INT |

### L — Live mode

| ID | Requirement | Target | Status | Notes |
|----|-------------|--------|--------|-------|
| L-1 | Live vs Resting toggle | v2.0 | **Done** | Orb toggle |
| L-2 | Orb visual states map to Live session | v2.0 | **Done** | `OrbWidget`, WS session |
| L-3 | Background listening + disclosure + notification | v2.2 | **Partial** | **Android C2 shipped early**; iOS foreground-only |
| L-4 | Text mode while Resting; voice requires Live | v2.0 | **Done** | Text chat + Live voice |

### T — Tasks and planning

| ID | Requirement | Target | Status | Notes |
|----|-------------|--------|--------|-------|
| T-1 | Daily plan: title, due, priority, status | v2.0 | **Done** | Tasks API + Today UI |
| T-2 | Voice/text task tools | v2.0 | **Done** | plan_extractor + confirm flow (C3a) |
| T-3 | Open tasks persist across sessions | v2.0 | **Done** | PostgreSQL tasks |
| T-4 | Read-only device calendar import | v2.1 | **Not started** | C4 deferred |
| T-5 | Two-way calendar sync | v2.2 | **Not started** | Backlog |

### DLY — Daily activity loop

| ID | Requirement | Target | Status | Notes |
|----|-------------|--------|--------|-------|
| DLY-1 | Morning brief at user-configured time | v2.0 | **Partial** | API `morning-payload`; notification UX maturity varies |
| DLY-2 | Evening recap + defer carry-over | v2.0 | **Partial** | API `evening-payload`; full recap UX not as rich as spec |
| DLY-3 | Calm achievement summary | v2.0 | **Partial** | Contract exists; polish TBD |
| DLY-4 | Proactive check-in when user quiet | v2.1 | **Partial** | C3b task nudges shipped; broad quiet-user check-in not |

### INT — Integrations

| ID | Requirement | Target | Status | Notes |
|----|-------------|--------|--------|-------|
| INT-1 | Per-integration opt-in in Settings | v2.1 | **Not started** | [`backlog/epic-integrations.md`](backlog/epic-integrations.md) only |
| INT-2 | Spotify OAuth + play_music | v2.1 | **Not started** | Deferred v2.1+ |
| INT-3 | Media controls / Apple MusicKit | v2.2 | **Not started** | Deferred v2.2 |
| INT-4 | Maps/timer deep links | v2.2 | **Not started** | Deferred v2.2 |

### Backlog epic drift (documentation debt)

| Epic file | Problem |
|-----------|---------|
| [`backlog/epic-registration.md`](backlog/epic-registration.md) | R-1–R-4 still `[ ]` — **shipped** |
| [`backlog/epic-daily-loop.md`](backlog/epic-daily-loop.md) | T-1–T-3, DLY-1–3 still `[ ]` — **mostly shipped** |
| [`backlog/epic-integrations.md`](backlog/epic-integrations.md) | Correctly not started |

Reconcile epics in a separate hygiene pass; **this file is the status source of truth.**

---

## 4. Ops and infrastructure deliverables

Sources: [`done/ops-deploy-2026-06-09.md`](done/ops-deploy-2026-06-09.md), [`done/v1-decommission-2026-06-09.md`](done/v1-decommission-2026-06-09.md), [`done/phase0-bootstrap.md`](done/phase0-bootstrap.md)

| Item | Status | Evidence | Improvement needed |
|------|--------|----------|-------------------|
| `/home/dev/docs` hub + `this repository` monorepo | **Done** | phase0-bootstrap | — |
| PostgreSQL (`aipal-postgres-1` :5432) | **Done** | ops-deploy | — |
| API v2 deployed `/opt/aipal-v2` → `:8102` | **Done** | systemd `aipal-v2.service` | — |
| Caddy: `/api/v2/*` → 8102; `/app/` Flutter web | **Done** | v1-decommission | — |
| `dev` passwordless sudo + docker group | **Done** | ops-deploy | — |
| Flutter 3.44.1 + Android SDK on VM | **Done** | `/opt/flutter`, `/opt/android-sdk` | — |
| v1 MVP decommission (`/opt/aipal` removed) | **Done** | v1-decommission | Optional: remove `/etc/default/aipal`, `/var/lib/aipal`, old systemd unit |
| Ansible deploy-v2 playbook | **Done** | phase0-bootstrap | — |
| Production health | **Done** | `https://43.160.220.9.sslip.io/api/v2/health` | — |

---

## 5. Release and distribution deliverables

| Item | Status | Notes |
|------|--------|-------|
| Play API automation (fastlane + service account) | **Done** | [`done/play-api-automation-2026-06-09.md`](done/play-api-automation-2026-06-09.md) |
| First Play Internal upload (v2.0.0+6) | **Done** | [`done/play-api-upload-internal-2026-06-09.md`](done/play-api-upload-internal-2026-06-09.md) |
| Current Play Internal build | **Done** | **2.4.0+18** — C2 background wake |
| `deploy-android-internal.sh` / `deploy-android-apk-dev.sh` | **Done** | [`../scripts/`](../scripts/) |
| Flutter web at `/app/` | **Done** | Text mode; voice native-only |
| Stakeholder status page at `/status/` | **Done** | Password-protected; generated from this doc + ROADMAP on deploy |
| APK sideload `/downloads/aipal-latest.apk` | **Done** | v1-decommission |
| iOS TestFlight pipeline | **Not done** | Needs macOS; see [`releases/IOS_TESTFLIGHT.md`](releases/IOS_TESTFLIGHT.md) |
| GitHub repo `tfasanya79/aipal` | **Done** | Private; initial push complete |

### Release history snapshots (`done/`)

| Snapshot | Milestone |
|----------|-----------|
| [`phase0-bootstrap.md`](done/phase0-bootstrap.md) | Monorepo, API, Flutter scaffold, CI |
| [`ops-deploy-2026-06-09.md`](done/ops-deploy-2026-06-09.md) | VM deploy, Caddy, AAB build |
| [`voice-ux-v8-2026-06-09.md`](done/voice-ux-v8-2026-06-09.md) | Tap-once Live, live greeting (versionCode 8) |
| [`v1-decommission-2026-06-09.md`](done/v1-decommission-2026-06-09.md) | v1 removed; web v2 at `/app/` |
| [`play-api-automation-2026-06-09.md`](done/play-api-automation-2026-06-09.md) | fastlane + Play JSON setup |
| [`play-api-upload-internal-2026-06-09.md`](done/play-api-upload-internal-2026-06-09.md) | First automated Internal upload |

---

## 6. QA, testing, and agent tooling

| Item | Status | Location |
|------|--------|----------|
| Brain pytest suite | **Done** | `apps/api/tests/test_brain_v11.py` |
| API CI (pytest + ruff) | **Done** | `.github/workflows/api-ci.yml` |
| Mobile CI (`flutter analyze`) | **Done** | `.github/workflows/mobile-ci.yml` |
| Release smoke script | **Done** | `scripts/smoke-test.sh` |
| Release QA subagent | **Done** | `.cursor/agents/release-qa-agent.md` |
| Cursor skill: `aipal-brain` | **Done** | `.cursor/skills/aipal-brain/` |
| Cursor skill: `aipal-brand` | **Done** | `.cursor/skills/aipal-brand/` |
| Cursor skill: `aipal-release` | **Done** | `.cursor/skills/aipal-release/` |
| Cursor skill: `aipal-mobile` | **Done** | `.cursor/skills/aipal-mobile/` |
| Cursor skill: `aipal-testers` | **Done** | `.cursor/skills/aipal-testers/` |
| Cursor skill: `aipal-project-sync` | **Done** | `.cursor/skills/aipal-project-sync/` |
| GitHub Project sync script + workflow | **Done** | `scripts/sync_github_project.py`, `.github/workflows/sync-project.yml`; [`.github/project.json`](../.github/project.json) tracked on `main` (project #24) |

---

## 7. Documentation deliverables

| Document | Status | Improvement |
|----------|--------|-------------|
| `/home/dev/docs` hub ([`README.md`](README.md)) | **Done** | Link to this file (added) |
| **DELIVERABLES.md** (this file) | **Done** | Refresh on phase ship / release |
| [`PRODUCT.md`](PRODUCT.md) | **Done, current** | Canonical phase checklists |
| [`stakeholder/ROADMAP.md`](stakeholder/ROADMAP.md) | **Done** | Stakeholder narrative |
| [`architecture/feature-spec-v2.md`](architecture/feature-spec-v2.md) | **Done** | Living spec |
| [`architecture/requirement-file-v2.md`](architecture/requirement-file-v2.md) | **Done** | Add status column optional follow-up |
| ADRs 001–006 | **Done** | [`decisions/`](decisions/) |
| [`releases/CHANGELOG.md`](releases/CHANGELOG.md) | **Stale** | Stops at 2.0.0; needs 2.1–2.4 entries |
| [`releases/VERSION_MATRIX.md`](releases/VERSION_MATRIX.md) | **Stale** | Still references v1 on 8101 and Android 2.0.0+6 |
| [`ongoing/sprint-01.md`](ongoing/sprint-01.md) | **Stale** | Marked "in progress" but checklist complete |
| [`backlog/*.md`](backlog/) | **Stale** | Epics not updated post-ship |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | **Done** | Tester + maintainer guide |

---

## 8. Gaps, risks, and recommended improvements

### Product (deferred / not started)

- **Sensitivity slider** for wake word (C1/C2) — deferred; threshold hard-coded
- **Richer mem0 retrieval every turn** (C4) — not started
- **Calendar import** (C4 / T-4) — not started
- **Morning/evening brief UX** — API contracts exist; end-to-end daily loop polish below spec ambition

### Platform parity

- **iOS background wake** — foreground-only today; Shortcuts path TBD
- **iOS TestFlight** — no macOS on Tencent VM; needs GitHub Actions secrets or local Mac ([`IOS_TESTFLIGHT.md`](releases/IOS_TESTFLIGHT.md))

### Documentation hygiene

- Update [`CHANGELOG.md`](releases/CHANGELOG.md) for releases through **2.4.0+18**
- Update [`VERSION_MATRIX.md`](releases/VERSION_MATRIX.md) (remove v1 row; current Android/API versions)
- Reconcile [`backlog/`](backlog/) epic checkboxes or archive to `done/`
- Close or archive [`ongoing/sprint-01.md`](ongoing/sprint-01.md)

### Tooling / process

- **GitHub Project board** — **Done** (AiPal Roadmap, ~32 items; sync on `docs/PRODUCT.md` changes via **Sync GitHub Project** workflow)
- **Regression verification** — formalize periodic run of PRODUCT.md scenarios in release QA

### Ops (optional)

- Remove orphaned v1 artifacts: `/etc/default/aipal`, `/var/lib/aipal`, `aipal.service` unit file ([`v1-decommission`](done/v1-decommission-2026-06-09.md))

### Inherited v1 requirements (A–Q)

v2 does not re-audit every v1 requirement ID. Safety, crisis handling, and export/clear are assumed carried forward. Full v1 table: `/o../requirement-file.md` (historical; v1 decommissioned).

---

## 9. Maintenance rules

1. **Phase ship** — Update [`PRODUCT.md`](PRODUCT.md) checkboxes first, then refresh **Section 2** and the executive summary in this file.
2. **Release** — Bump `pubspec.yaml`; update this file, [`CHANGELOG.md`](releases/CHANGELOG.md), and [`VERSION_MATRIX.md`](releases/VERSION_MATRIX.md); add a one-line entry under Section 5 if milestone-worthy.
3. **Ops milestone** — Add a dated snapshot under [`done/`](done/) and reference it in Section 4 or 5.
4. **New requirement** — Add row to Section 3 and to [`requirement-file-v2.md`](architecture/requirement-file-v2.md).
5. **Stakeholder comms** — Keep [`stakeholder/ROADMAP.md`](stakeholder/ROADMAP.md) Now/Next aligned with Section 8 gaps.

**Do not** treat [`backlog/`](backlog/) epics as live status until reconciled with this tracker.

---

## Related links

| Resource | Path |
|----------|------|
| Product phases (canonical) | [`PRODUCT.md`](PRODUCT.md) |
| Stakeholder roadmap | [`stakeholder/ROADMAP.md`](stakeholder/ROADMAP.md) |
| Feature spec | [`architecture/feature-spec-v2.md`](architecture/feature-spec-v2.md) |
| OpenAPI | [`architecture/openapi-v2.yaml`](architecture/openapi-v2.yaml) |
| Play Internal notes | [`releases/PLAY_INTERNAL_v2.md`](releases/PLAY_INTERNAL_v2.md) |
