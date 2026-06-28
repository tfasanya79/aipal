"""Session-scoped NDJSON debug logging for device QA (AGENT_DEBUG=1)."""

from __future__ import annotations

import json
import logging
import os
import time

log = logging.getLogger("aipal.agent_debug")

DEBUG_LOG_PATHS = (
    "/var/log/aipal/debug-60ce92.log",
    "/home/dev/.cursor/debug-60ce92.log",
)
SESSION_ID = "60ce92"


def agent_debug(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
    *,
    run_id: str = "pre-fix",
) -> None:
    if os.environ.get("AGENT_DEBUG") != "1":
        return
    entry = {
        "sessionId": SESSION_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": run_id,
    }
    line = json.dumps(entry)
    log.info("AGENT_DEBUG %s", line)
    for path in DEBUG_LOG_PATHS:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return
        except OSError:
            continue
