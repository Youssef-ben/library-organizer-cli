from __future__ import annotations

import json
import sys
from typing import Protocol


class ProgressCallback(Protocol):
    """
    Progress callback contract used by the CLI for both text and JSON modes.

    Producers typically pass:
      - current, total, stage(prefix), phase, file

    For byte-based phases they may also pass:
      - file_size_bytes, processed_bytes, total_bytes
    """

    def __call__(
        self,
        current: int,
        total: int,
        prefix: str,
        phase: str,
        file: str | None = None,
        file_size_bytes: int | None = None,
        processed_bytes: int | None = None,
        total_bytes: int | None = None,
    ) -> None: ...

def _json_progress(*args) -> None:
    # Supports signature:
    # -  cb(current, total, prefix, phase)
    # -  cb(current, total, prefix, phase, file | None)
    # -  cb(current, total, prefix, phase, file | None, file_size_bytes,
    #        processed_bytes, total_bytes)
    current, total, prefix, phase = args[:4]
    file = args[4] if len(args) > 4 else None
    file_size_bytes = args[5] if len(args) > 5 else None
    processed_bytes = args[6] if len(args) > 6 else None
    total_bytes = args[7] if len(args) > 7 else None

    if total <= 0:
        return

    stage = str(prefix).strip()
    payload = {
        "type": "progress",
        "stage": stage,
        "phase": phase or stage,
        "current": current,
        "total": total,
        "file": file,
        "file_size_bytes": file_size_bytes,
        "processed_bytes": processed_bytes,
        "total_bytes": total_bytes,
    }

    print(json.dumps(payload), flush=True)

def _print_progress(current: int, total: int, prefix: str = "Progress") -> None:
    """Prints a single-line dynamic progress bar to the terminal."""
    percent = (current / total) * 100
    bar_length = 40
    filled_length = int(bar_length * current // total)
    bar = "#" * filled_length + "-" * (bar_length - filled_length)
    sys.stdout.write(f"\r{prefix}: |{bar}| {percent:.1f}% ({current}/{total})")
    sys.stdout.flush()
    if current == total:
        print()

def _text_progress(*args) -> None:
    # Supports signature:
    # -  cb(current, total, prefix)
    # -  cb(current, total, prefix, phase | None, file | None)
    # Producers for JSON mode may pass additional args; ignore them.
    if len(args) < 3:
        return
    current, total, prefix = args[0], args[1], args[2]

    if total <= 0:
        return

    if prefix == "Discovering":
        return

    _print_progress(current, total, prefix)

def progress_callback_builder(progress_format: str) -> ProgressCallback:
    """Build a progress callback for the chosen output format (text or JSON).
        Example:
        - JSON: callback(current, total, prefix, phase, file | None)
        - Text: callback(current, total, prefix)
    """
    if progress_format == "json":
        return _json_progress

    return _text_progress

