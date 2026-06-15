# Requirements: Handsfree Go Live MVP and completion scope

*Mapping: **ID** = stable reference for [development-ToDo.md](./development-ToDo.md) and test cases. **Priority:** P0 (must for MVP) / P1 / P2.*

---

## A — Acoustic and affect (UX only, non-clinical)

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| A-1 | Compute at least one acoustic descriptor (for example RMS) where technically feasible | P0 | Yes |
| A-2 | Combine text sentiment and acoustic hint into a broad mood signal for prompt adaptation only | P0 | Yes |
| A-3 | Never present affect output as diagnosis or treatment recommendation | P0 | Yes |
| A-4 | UI must clearly state affect output is supportive, not clinical | P0 | Yes |

## B — Branding and product positioning

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| B-1 | In-app disclaimer: not a substitute for emergency or professional care | P0 | Yes |
| B-2 | External marketing copy reviewed before public launch | P1 | No |

## C — Crisis and safety

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| C-1 | Keyword and heuristic safety checks on user speech text (final transcript at minimum) | P0 | Yes |
| C-2 | Templated crisis response with configurable regional resources | P0 | Partial |
| C-3 | No self-harm/harmful instruction generation; red-team tests for known prompt classes | P0 | Partial |
| C-4 | Log safety-path activation metadata for post-test review | P1 | Partial |

## D — Data controls

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| D-1 | User can export session transcript | P0 | Yes |
| D-2 | User can clear profile + session data from server store | P0 | Yes |
| D-3 | Local/self-host default posture: no external training pipeline on user data | P0 | Yes |

## E — Scope boundary (non-MVP)

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| E-1 | Therapist marketplace, clinician workflow, and payer features are out of MVP | P0 | N/A |
| E-2 | Monetization tiers are documented as post-MVP work | P1 | Doc only |

## F — Conversation functionality (handsfree first)

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| F-1 | App supports one-time **Go Live** session start/stop lifecycle | P0 | Yes |
| F-2 | Turn-taking uses VAD/silence endpointing in Go Live mode | P0 | Yes; reference-device validation pending |
| F-3 | Speech-to-text pipeline supports conversational turns (streaming or chunked path documented) | P0 | Yes; chunked path |
| F-4 | LLM reply generated with companion prompt and safety constraints | P0 | Yes |
| F-5 | Voice reply auto-play in Go Live mode (no extra button each turn) | P0 | Yes; reference-device validation pending |
| F-6 | Push-to-talk remains available as temporary fallback during MVP hardening | P0 | Yes (temporary) |
| F-7 | Fallback deprecation gate must be explicitly documented before stakeholder pilot expansion | P1 | Target |

## G — Governance and legal

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| G-1 | Product owner obtains jurisdiction-appropriate legal review for health-adjacent copy | P0 | Process |
| G-2 | Privacy policy and terms prepared before broad external launch | P1 | Internal privacy policy live; full legal package pending |

## H — Human escalation (future)

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| H-1 | If clinician escalation is added, explicit consent + access controls are mandatory | P0 | Defer |
| H-2 | User-initiated transcript sharing path to humans is preserved | P1 | Export only |

## I — Accessibility and mobile UX

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| I-1 | Mobile-first layout for primary flows | P0 | Yes |
| I-2 | Core controls remain accessible (labels/focus/contrast baseline) | P1 | Partial |
| I-3 | Handsfree session behavior documented for phone constraints (permissions, screen state, audio route) | P0 | Partial; Android internal testing next |

## M — Memory and personalization

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| M-1 | About-me profile persisted | P0 | Yes |
| M-2 | Rolling short context memory for recent turns | P0 | Yes |
| M-3 | Long-term vector memory is deferred | P2 | Defer |

## N — Non-functional performance targets

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| N-1 | Health endpoint available for liveness and dependency check | P0 | Yes |
| N-2 | Publish target hardware profile and latency targets in runbook | P0 | Yes; reference-device matrix pending |
| N-3 | Go Live mode target: turn-end to first assistant audio p95 <= 5s on reference setup (warm path) | P0 | Target |
| N-4 | Session stability target: >= 30 minutes continuous run without crash on reference mobile setup | P1 | Target |

## O — Observability

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| O-1 | Structured logs to stdout/journal | P0 | Yes |
| O-2 | Basic deploy/runbook diagnostics for field debugging | P0 | Yes |
| O-3 | Metrics/dashboard stack optional post-MVP | P1 | Defer |

## P — Platform and deployment strategy

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| P-1 | Hybrid track is official: web Go Live-lite now, native mobile track in parallel | P0 | Yes; Android internal release published |
| P-2 | HTTPS public deployment path documented and repeatable | P0 | Yes |
| P-3 | Web/PWA client remains stakeholder demo surface while native app matures | P0 | Yes |

## Q — Quality and validation

| ID | Requirement | Priority | MVP |
|----|-------------|----------|-----|
| Q-1 | Manual stakeholder demo script aligned to Go Live-first story | P0 | Yes; installed-app run pending |
| Q-2 | Automated smoke tests for health/profile plus documented voice test checklist | P1 | Partial |
| Q-3 | Red-team checklist executed per release candidate, including handsfree-specific failure modes | P0 | Target |

---

## Explicit MVP acceptance gate (handsfree stakeholder MVP)

MVP is acceptable for stakeholder sharing only when all are true:

1. **Go Live lifecycle works** (`F-1`, `F-2`) on reference devices.
2. **Voice reply auto-play works** without per-turn button (`F-5`).
3. **Safety path remains enforced** (`C-1` to `C-3`).
4. **Published latency/stability evidence** meets `N-2` and `N-3`.
5. **Fallback status is explicit** (`F-6`, `F-7`) and not presented as final UX.

---

**Traceability rule:** every P0 requirement appears as a checkable item in [development-ToDo.md](./development-ToDo.md) or linked issue.
