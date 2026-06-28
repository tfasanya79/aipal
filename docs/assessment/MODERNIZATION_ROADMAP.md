# AiPal — modernization roadmap (outline)

**Provenance:** Chat export 2026-06-27, **reconciled** with canonical freeze rules. See [`SOURCE.md`](SOURCE.md) and [`COMPARISON.md`](COMPARISON.md).

---

## Gate zero: voice trust (before Phase 1 below)

Pass [VOICE_BASELINE.md](../releases/VOICE_BASELINE.md) device QA gates 1–7 on current Play Internal build.

**Do not** start C6 full-duplex or streaming LLM until this gate clears.

---

## Phase 1 — Reliability + intelligence (Q3 2026)

| Initiative | Assessment claim | Canonical action |
|------------|------------------|------------------|
| Wake reliability | Fix Hi Pal / phantom Live | **In progress** builds 59–61; v0.2 model if gate fails |
| STT ambient guards | Filter TV/noise transcripts | **Shipped** partial in router.py; extend as needed |
| Active memory | mem0 influences replies | **Backlog** — context_builder scoring |
| Multi-step reasoning | Decompose complex plans | **Backlog** — after voice stable |
| Semantic extraction | Replace regex | **Conflict** — already LLM JSON; improve gating only |
| Full-duplex v2 | Phase 1 recovery | **Forbidden** until ADR unfreeze |
| E2E tests | Onboarding → confirm → Today | **Net new** — safe to implement |

---

## Phase 2 — Platform + quality (Q4 2026)

- iOS background wake (C2 parity)
- macOS / Windows clients (optional)
- E2E + stress tests (>80% **non-voice** coverage target)
- Observability: Prometheus metrics, Grafana dashboards (**not started**)
- 99.5% uptime target on single VM first

---

## Phase 3 — Ecosystem + scaling (2027)

- Calendar OAuth (beyond read-only device calendar)
- Messaging draft compose (C4+ deferred in PRODUCT)
- Kubernetes / multi-region (**not started**)
- Smart home / music integrations (exploratory)

---

## Assessment “Week 1–2” proposals — disposition

| Proposal | Verdict |
|----------|---------|
| Multi-step reasoning in plan_extractor | Backlog after voice gate |
| Replace regex with LLM extractor | Reject — already LLM |
| Active memory in context_builder | Merge to backlog |
| Preference learning endpoints | Net new — design first |
| E2E test suite | **Do** — non-voice paths |
| Prometheus setup | Net new — ops backlog |
| AppState refactor | **Defer** — high risk during wake fixes |

---

## Success metrics (aspirational)

- Voice: gates 1–7 pass; <500ms perceived latency (half-duplex milestone)
- Brain: 95%+ booking/reschedule accuracy on device QA scripts
- Ops: metrics dashboard before multi-region
