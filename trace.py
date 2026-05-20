"""JSONL tracing for agent runs.

Tracing is intentionally append-only and optional. Set TRACE_PATH to choose a
file; otherwise traces are written under traces/ with a timestamped name.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


TRACE_PATH = os.getenv("TRACE_PATH")
RUN_ID = os.getenv("RUN_ID") or datetime.now().strftime("run-%Y%m%d-%H%M%S-%f")


def _default_trace_path() -> Path:
    return Path("traces") / f"{RUN_ID}.jsonl"


def trace_path() -> Path:
    return Path(TRACE_PATH) if TRACE_PATH else _default_trace_path()


def new_turn_id() -> str:
    return f"turn-{uuid4().hex[:12]}"


def write_event(event: dict) -> None:
    path = trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        **event,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
