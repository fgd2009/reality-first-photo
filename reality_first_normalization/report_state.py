"""Atomic checkpoints inside a newly created, exclusively owned run directory."""
from __future__ import annotations

import json
import os
from pathlib import Path


def write_json(path: Path, report: dict) -> None:
    """Keep the previous valid checkpoint if serialization or writing fails.

    This is a process-interruption safeguard, not a filesystem transaction or a
    guarantee against power loss. Never call it on an existing user's run.
    """
    payload = json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    owned = False
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            owned = True
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if owned:
            temporary.unlink(missing_ok=True)
