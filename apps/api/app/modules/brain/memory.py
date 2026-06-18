import logging
from typing import Any

from app.shared.config import get_settings

log = logging.getLogger("aipal.memory")
_settings = get_settings()
_memory = None


def get_memory():
    global _memory
    if not _settings.mem0_enabled:
        return None
    if _memory is not None:
        return _memory
    try:
        from mem0 import Memory

        _memory = Memory()
        return _memory
    except Exception as exc:
        log.warning("Mem0 unavailable: %s", exc)
        return None


def memory_add(user_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
    m = get_memory()
    if not m:
        return
    try:
        m.add(text, user_id=user_id, metadata=metadata or {})
    except Exception as exc:
        log.warning("mem0 add failed: %s", exc)


def memory_search(user_id: str, query: str, limit: int = 5) -> list[str]:
    m = get_memory()
    if not m:
        return []
    try:
        results = m.search(query, user_id=user_id, limit=limit)
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
