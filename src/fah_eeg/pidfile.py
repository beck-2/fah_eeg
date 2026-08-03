"""Tiny PID file helpers for CLI processes."""

from __future__ import annotations

import os
from pathlib import Path


def write_pid(path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")


def clear_pid(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
