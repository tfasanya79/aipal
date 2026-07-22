import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.shared.config import get_settings

log = logging.getLogger("aipal.memory")
_settings = get_settings()
_memory = None

# Persistent, per-user-owned storage for mem0's local Qdrant vector store. Deliberately kept
# OUTSIDE any deploy path (e.g. /opt/aipal-v2/apps/api) so `rsync --delete` during deploys can
# never wipe it, and outside /tmp so memories survive reboots. Override with MEM0_DATA_DIR if
# ever needed (e.g. a shared data volume).
_MEM0_DATA_DIR = os.environ.get("MEM0_DATA_DIR") or str(Path.home() / ".aipal" / "mem0_qdrant")
# Small, free, local ONNX embedding model (no API key, no torch/GPU needed) - fastembed loads it
# once and reuses it in-process. 384-dim; must match the vector store's embedding_model_dims below.
_MEM0_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_MEM0_EMBED_DIMS = 384


def _mem0_llm_config() -> dict | None:
    """mem0 needs its own LLM for internal fact-extraction from conversation text. Reuse the
    app's already-configured, already-paid-for provider/key instead of mem0's undocumented
    hard default (OpenAI), which is why mem0 has been failing on every call in production.
    """
    if _settings.anthropic_api_key:
        return {
            "provider": "anthropic",
            "config": {
                "model": _settings.anthropic_model,
                "api_key": _settings.anthropic_api_key,
            },
        }
    if _settings.deepseek_api_key:
        return {
            "provider": "deepseek",
            "config": {
                "model": "deepseek-chat",
                "api_key": _settings.deepseek_api_key,
                "deepseek_base_url": "https://api.deepseek.com",
            },
        }
    return None


def _build_memory_config() -> dict:
    Path(_MEM0_DATA_DIR).mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {
        "embedder": {
            "provider": "fastembed",
            "config": {
                "model": _MEM0_EMBED_MODEL,
                "embedding_dims": _MEM0_EMBED_DIMS,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": _MEM0_DATA_DIR,
                "embedding_model_dims": _MEM0_EMBED_DIMS,
            },
        },
    }
    llm_config = _mem0_llm_config()
    if llm_config:
        config["llm"] = llm_config
    return config


def get_memory():
    global _memory
    if not _settings.mem0_enabled:
        return None
    if _memory is not None:
        return _memory
    try:
        from mem0 import Memory

        _memory = Memory.from_config(_build_memory_config())
        return _memory
    except Exception as exc:
        log.warning("Mem0 unavailable: %s", exc)
        return None


def memory_add(
    user_id: str,
    text: str,
    *,
    kind: str = "fact",
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    m = get_memory()
    if not m:
        return
    meta = dict(metadata or {})
    meta.setdefault("kind", kind)
    meta.setdefault("date", datetime.now(UTC).date().isoformat())
    if session_id:
        meta.setdefault("session_id", session_id)
    try:
        m.add(text, user_id=user_id, metadata=meta)
    except Exception as exc:
        log.warning("mem0 add failed: %s", exc)


def remember_turn(
    user_id: str,
    *,
    role: str,
    text: str,
    session_id: str,
    kind: str | None = None,
) -> None:
    """Structured mem0 write after a conversation turn."""
    if not text.strip():
        return
    label = "User" if role == "user" else "AiPal"
    inferred_kind = kind or ("plan" if role == "assistant" and "today" in text.lower() else "fact")
    memory_add(
        user_id,
        f"{label}: {text.strip()[:500]}",
        kind=inferred_kind,
        session_id=session_id,
    )


def memory_search(user_id: str, query: str, limit: int = 5) -> list[str]:
    m = get_memory()
    if not m:
        return []
    try:
        results = m.search(query, filters={"user_id": user_id}, top_k=limit)
        if isinstance(results, dict) and "results" in results:
            return [r.get("memory", r.get("text", "")) for r in results["results"]]
        if isinstance(results, list):
            return [str(r) for r in results]
    except Exception as exc:
        log.warning("mem0 search failed: %s", exc)
    return []


def memory_delete_user(user_id: str) -> None:
    m = get_memory()
    if not m:
        return
    try:
        m.delete_all(user_id=user_id)
    except Exception as exc:
        log.warning("mem0 delete failed: %s", exc)
