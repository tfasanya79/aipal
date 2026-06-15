# Project goal: explicit plan and 100% completion definition

This document is the source of truth for what “done” means for AIpal as a **handsfree companion** product. The approved strategy is:

- **Hybrid delivery**: web Go Live-lite for near-term demos + native mobile track in parallel.
- **Interaction default**: one-time **Go Live** session with VAD turn-taking.
- **Risk control**: push-to-talk is temporary fallback, not final UX.

---

## Vision (final state)

AIpal is a voice-first companion for hands-busy moments (for example driving or chores) with clear guardrails, non-clinical positioning, and safety-first behavior. Users can start one live session, speak naturally, and hear concise replies without per-turn button friction. The system adapts tone using broad affect signals and sentiment for UX support only, never diagnosis.

When serious risk appears, AIpal routes to crisis-safe responses and vetted resources. Any clinical or therapist workflow remains outside baseline MVP unless explicitly re-scoped.

**100% completion** means all non-deferred requirements in [requirement-file.md](./requirement-file.md) are implemented, tested, and documented with evidence.

---

## Phased roadmap to completion

### Phase 0 — Docs reset and scope alignment (completed)

- Rewrite charter docs to the approved handsfree hybrid strategy.
- Re-map requirements and execution checklist to Go Live + VAD.
- Align stakeholder presentation and runbook language to handsfree-first.

**Exit gate:** all core docs and to-dos are synchronized with the new requirement IDs and MVP gates.

### Phase 1A — Web Go Live-lite MVP (near-term stakeholder path)

- Keep current web/PWA surface but move primary story to Go Live session lifecycle.
- Document and implement turn-taking behavior (VAD/silence policy), auto voice response target, and fallback boundaries.
- Validate HTTPS deployment, smoke checks, and safety red-team flow for stakeholder demos.

**Exit gate:** stakeholder demo can run end-to-end with handsfree-first narrative, measurable latency/stability evidence, and explicit fallback caveat.

### Phase 1B — Native mobile foundation (active)

- **Ship installable clients first** with **Capacitor** wrapping the existing React/Vite UI (`mvp/frontend` → `android/` + `ios/`), calling the **hosted HTTPS API** (e.g. Tencent / sslip). See [mvp/docs/M1-INTERNAL-BUILDS.md](mvp/docs/M1-INTERNAL-BUILDS.md).
- Android Play Internal testing release is published as version code `3` / version `1.0.2`; tester opt-in and reference-device acceptance remain before M1 is complete.
- **Optional later:** React Native or Flutter if WebView audio/Bluetooth limits block Go Live parity on reference devices.
- Establish real-time session interface parity with web path.
- Define device test matrix (iOS/Android, headset/Bluetooth, network conditions).

**Exit gate:** internal **Play** / **TestFlight** builds pass the M1 checklist; roadmap to full Go Live parity documented.

### Phase 2 — Product hardening and pilot readiness

- Auth, encrypted persistence, consent UX, deletion policy fit.
- Automated regression/safety checks + operational runbooks.
- Privacy/legal copy and launch controls aligned with region.

**Exit gate:** controlled pilot readiness with documented risk posture.

### Phase 3 — Commercial/regulated extensions (optional)

- Clinical/commercial boundary decisions per market.
- Optional partner workflows (therapist/employer/payer) as separate tracks.

**Exit gate:** region-specific signed launch checklist.

---

## MVP definition for current stakeholder cycle

MVP for this cycle is **not** “all final product features.” It is:

1. Handsfree-first Go Live narrative and requirement baseline.
2. Working stakeholder demo path on deployed environment.
3. Evidence-backed performance/safety expectations with known limits.

Push-to-talk may remain present only as temporary fallback with explicit removal criteria.

---

## Definition: “100% project goal” (final)

The project is 100% complete when all are true:

1. **Functionality:** non-deferred requirements implemented (especially F/C/N/P groups).
2. **Safety:** red-team and crisis handling coverage demonstrates no unresolved critical classes.
3. **Data governance:** inspect/export/delete controls and policy alignment are complete.
4. **Operability:** repeatable deploy, monitoring, and recovery procedures exist.
5. **Evidence:** stakeholder sign-off and traceability from requirement -> test -> release.

Out of scope unless explicitly added: guaranteed 24/7 therapist access, EHR integration, or medical-device claims.

---

## Program-level success metrics

- **Latency:** Go Live turn-end to first assistant audio meets target band in requirement N group.
- **Stability:** reference continuous sessions meet documented minimum run duration.
- **Trust/Safety:** no unresolved critical safety findings in release candidate checklist.
- **Clarity:** stakeholders can complete demo flow without operator intervention.

This file must be updated whenever scope, legal posture, or MVP gates change.
