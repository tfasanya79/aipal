# AiPal — full-scope assessment (excerpt)

**Provenance:** Chat export 2026-06-27. See [`SOURCE.md`](SOURCE.md).

---

## Technology stack (verified in repo)

| Layer | Stack |
|-------|--------|
| Mobile | Flutter (Dart), Provider, `io.aipal.mvp` |
| API | FastAPI v2, PostgreSQL, async SQLAlchemy |
| LLM | DeepSeek |
| STT/TTS | Whisper (path), edge-tts |
| Wake | OpenWakeWord `hi_pal_v0.1.onnx` |
| Memory | mem0 (optional) |
| Deploy | Tencent VM, Caddy, Play Internal |

---

## Architecture strengths

- Modular monolith under `apps/api/app/modules/`
- Plan draft confirm flow separates understanding from commitment
- Session observability (`session_events`, agent debug)
- Targeted voice unfreeze process documented in VOICE_BASELINE

---

## Critical gaps (assessment vs. repo reality)

### 1. Voice path

- Production: half-duplex AAC → `POST /turn/audio` ([`VOICE_BASELINE.md`](../releases/VOICE_BASELINE.md))
- Known issues (builds 59–61): FGS/foreground route races, mic startup false wakes, ambient STT hallucinations
- C6 WebSocket full-duplex: **paused**, not production

### 2. Task extraction

Assessment claimed “regex-based extraction.” **Inaccurate:** [`plan_extractor.py`](../../apps/api/app/modules/brain/plan_extractor.py) uses **LLM JSON**; regex is used for **gating** (`needs_plan_extraction`) and edit signals only.

### 3. Memory

- `remember_turn` + mem0 on every turn
- Opportunity: stronger retrieval scoring in `context_builder` (backlog, not shipped)

### 4. Testing

- API: 70+ pytest tests, smoke script
- Mobile: widget/routing tests
- **Gap:** no automated substitute for device voice QA gates 1–7

### 5. Ops

- Single VM `43.160.220.9.sslip.io`
- No Prometheus/Grafana in repo (assessment proposal = net new)

---

## Risk inventory

| Risk | Mitigation |
|------|------------|
| Wake model trained on synthetic espeak | Retrain v0.2 with real clips ([`wake-word-engine.md`](../decisions/wake-word-engine.md)) |
| Parallel wake sync restarts | Serialized sync chain (build 59+) |
| LLM claims mutation without tools | Honesty guards in router (C5) |
| Doc drift | PRODUCT + DELIVERABLES + pubspec single source for version |

---

## See also

- [MODERNIZATION_ROADMAP.md](MODERNIZATION_ROADMAP.md)
- [COMPARISON.md](COMPARISON.md)
