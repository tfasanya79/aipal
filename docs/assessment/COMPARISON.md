# Assessment vs. canonical docs — comparison matrix

**Generated:** 2026-06-27  
**Assessment source:** Chat export (see [`SOURCE.md`](SOURCE.md)) — not original 130 KB files on disk.

## Git divergence at import time

| Ref | State |
|-----|--------|
| Local branch | `rollback/voice-38-freeze` (ahead of origin) |
| `origin/main` | `9a573c9` — Play **2.5.8+46** |
| Deploy / pubspec | **2.6.11+61** |
| Stale docs before merge | README `2.4.3+21`, DELIVERABLES `2.5.9+47`, CORE_PILLARS build **38** PASS |

---

## Comparison matrix

| Topic | Assessment claim | Canonical source | Verdict | Action |
|-------|------------------|------------------|---------|--------|
| Confirm-before-commit | Unique differentiator | PRODUCT C3a, PlanDraftCard | Agree | Already shipped; keep in ROADMAP narrative |
| On-device wake | OpenWakeWord privacy | wake-word-engine.md, PRODUCT C1/C2 | Agree | Document v0.2 retrain if gate fails |
| Voice latency >1s | vs. competitors <300ms | VOICE_BASELINE half-duplex | Agree | Defer streaming until gates pass |
| Full-duplex v2 Phase 1 | “Recovery” in Q3 | VOICE_BASELINE **Still forbidden** | **Conflict** | Keep C6 deferred; roadmap gate added |
| Voice code “locked” | No changes allowed | VOICE_BASELINE targeted unfreeze | Outdated | QUICK_REFERENCE + VOICE_WAKE_FROZEN pointer |
| Regex task extraction | Fragile regex-only | plan_extractor.py LLM JSON | **Conflict** | Correct in FULL_SCOPE excerpt; no rewrite |
| Multi-step reasoning | Single-turn LLM gap | C5 action_executor partial | Net new | ROADMAP backlog after voice gate |
| Active memory | mem0 passive | context_builder + remember_turn | Net new | ROADMAP backlog |
| Phantom STT / TV audio | Not in assessment | router.py ambient filters | Agree (gap) | Shipped 2.6.10+; extend as needed |
| Hi Pal false wake | Not detailed | wake_word_engine warmup, app_state suppress | Agree (gap) | Shipped 2.6.10–61; device QA |
| FGS/foreground race | Not in assessment | app_state lifecycle route | Agree (gap) | Shipped 2.6.11 |
| Testing ~30% coverage | Sparse | 73+ API pytest, flutter test, smoke | Outdated | DELIVERABLES: honest device E2E gap |
| E2E onboarding→Today | Proposed Week 1–2 | No automated E2E | Net new | DELIVERABLES backlog |
| Observability Prometheus | Phase 2 proposal | Not in repo | Net new | DELIVERABLES “not started” |
| iOS / desktop / watch | Platform gaps | PRODUCT C2 iOS partial | Agree | ROADMAP 2027 |
| Single VM ops | No failover | infra README | Agree | Phase 3 backlog |
| Calendar OAuth | Integration gap | C4 device calendar read-only | Agree | ROADMAP Q4 |
| AppState refactor | Week 4–5 proposal | app_state.dart frozen | **Conflict** | Defer until voice stable |
| Competitive table | AiPal vs Siri/Google | stakeholder/ROADMAP ideas | Duplicate | Merged aspirational table to ROADMAP |
| 9-month 3-phase roadmap | Q3/Q4/2027 | ROADMAP.md shorter | Duplicate | Extended ROADMAP with gates |
| Version numbers | Unspecified / wrong | pubspec 2.6.11+61 | Outdated | Fixed PRODUCT, README, DELIVERABLES |
| Wake model v0.2 | Not emphasized | wake-word-engine deferred | Agree | Keep deferred until gate #1 fails |
| `_HONEST_NOT_ADDED` spam | Not in assessment | router.py voice guard | Agree (gap) | Shipped 2.6.10 suppress on non-booking |

---

## Merge summary

| Verdict | Count | Handling |
|---------|-------|----------|
| Agree | 12 | Reinforced in canonical docs |
| Duplicate | 3 | Linked from assessment INDEX |
| Outdated | 4 | Corrected in canonical docs |
| Conflict | 4 | Documented; canonical wins |
| Net new | 5 | Added to ROADMAP/DELIVERABLES backlog |

---

## Authority order (when docs disagree)

1. `apps/mobile/pubspec.yaml` — shipped version
2. `docs/releases/VOICE_BASELINE.md` — voice freeze + QA gates
3. `docs/PRODUCT.md` — phase status
4. `docs/assessment/*` — stakeholder deep-dive + historical assessment
