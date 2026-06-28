# AiPal — quick reference

**Provenance:** Merged from assessment chat export + **canonical repo paths**. Prefer this over stale assessment claims.

---

## Repo layout

```
aipal/
  apps/mobile/          Flutter (Android, web)
  apps/api/             FastAPI v2
  docs/                 Product + ADRs
  scripts/              deploy-all.sh, smoke-test.sh
  .cursor/skills/       Agent skills (aipal-brain, aipal-mobile, …)
```

---

## Key files

| Area | Path |
|------|------|
| App state / wake / Live | `apps/mobile/lib/providers/app_state.dart` |
| Wake engine | `apps/mobile/lib/services/wake_word_engine.dart` |
| Live VAD loop | `apps/mobile/lib/services/live_voice_loop_io.dart` |
| Audio turns | `apps/api/app/modules/voice/router.py` |
| Plan extraction | `apps/api/app/modules/brain/plan_extractor.py` |
| Context / memory | `apps/api/app/modules/brain/context_builder.py` |
| Version | `apps/mobile/pubspec.yaml` |

---

## Voice freeze

- List: [`.github/VOICE_WAKE_FROZEN.md`](../../.github/VOICE_WAKE_FROZEN.md)
- Targeted unfreeze history: [`docs/releases/VOICE_BASELINE.md`](../releases/VOICE_BASELINE.md)
- **Still forbidden:** C6 full-duplex, LIVE_VOICE_V2, PCM streaming, sensitivity slider

Edits to frozen paths require explicit product-owner unfreeze + device QA.

---

## Common tasks

| Task | Command |
|------|---------|
| API tests | `cd apps/api && .venv/bin/python -m pytest tests/ -q` |
| Mobile tests | `cd apps/mobile && flutter test` |
| Deploy + Play | `UPLOAD_PLAY=1 bash scripts/deploy-all.sh` |
| Play AAB only | `bash scripts/deploy-android-internal.sh` |
| Smoke | `bash scripts/smoke-test.sh` |
| Health | `curl -sf https://43.160.220.9.sslip.io/api/v2/health` |

---

## Device QA (voice)

Run gates 1–7 from [`VOICE_BASELINE.md`](../releases/VOICE_BASELINE.md) on each Play Internal build before claiming voice fixed.

---

## Red flags

- “Implement full-duplex v2 now” — conflicts with freeze
- “Rewrite plan_extractor regex” — extractor is already LLM JSON
- Stale version in README — check `pubspec.yaml` first
- Merging `main` into rollback branch without review — divergent voice lines

---

## Escalation

1. Check [`COMPARISON.md`](COMPARISON.md) for assessment vs. canonical conflicts
2. Update [`PRODUCT.md`](../PRODUCT.md) when a phase ships
3. Log voice regressions in agent debug + `session_events`
