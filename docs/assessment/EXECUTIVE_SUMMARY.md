# AiPal — executive summary

**Provenance:** Chat export 2026-06-27. See [`SOURCE.md`](SOURCE.md).

---

## What AiPal is

A **handsfree voice companion**: users talk naturally; AiPal proposes plans for **Today**, asks once to confirm, and nudges before commitments. Differentiators: confirm-before-commit, visual Today, proactive nudges, on-device “Hi Pal” wake.

---

## Strengths (assessment agrees with repo)

- **Confirm-before-commit** — no silent task creation
- **Visual Today** — priority lanes, focus timer, routine chips
- **Proactive nudges** — ~12 min before due with guardrails
- **On-device wake** — OpenWakeWord; privacy-first for wake phrase
- **Handsfree-first** — Live + wake from phase C, not bolted on

---

## Critical gaps (prioritized for product trust)

1. **Voice reliability** — Hi Pal listener stability, false wakes, phantom Live replies (device QA gates 1–7 not consistently passing as of build 61 QA)
2. **Voice latency** — half-duplex + non-streaming LLM; >1s typical vs. ~300ms competitors
3. **STT ambient noise** — TV/room audio transcribed as user speech; requires client + server guards
4. **Memory depth** — mem0 stores turns; retrieval influence on replies can be deepened
5. **Platform** — Android primary; iOS wake partial; no desktop/wearables
6. **Ops** — single Tencent VM; no multi-region failover
7. **Integrations** — device calendar read-only; no OAuth sync

---

## Recommended sequencing (merged with canonical docs)

| Priority | Focus | Gate |
|----------|-------|------|
| **P0** | Voice trust — wake, orb end, quiet-room phantom speech | VOICE_BASELINE gates 1–7 |
| **P1** | Brain quality — active memory, multi-step planning | After P0 |
| **P2** | E2E tests (non-voice), observability | Parallel, low risk |
| **P3** | Platform parity, integrations, scaling | 2027 |

**Deferred:** C6 full-duplex v2 until explicit ADR unfreeze ([`live-voice-v2.md`](../decisions/live-voice-v2.md)).

---

## Competitive snapshot (aspirational Q4 2026)

| Aspect | AiPal today | Target | Siri/Google/Alexa |
|--------|-------------|--------|-------------------|
| Voice latency | >1s | <500ms (half-duplex first) | ~200–250ms |
| Task accuracy | ~80% voice | 95%+ | ~90% |
| Confirm-before-commit | Yes | Yes | No |
| On-device wake | Yes (Android) | + iOS C2 | Platform-native |

---

## Related

- [COMPARISON.md](COMPARISON.md) — what to merge vs. reject
- [stakeholder/ROADMAP.md](../stakeholder/ROADMAP.md) — updated canonical roadmap
