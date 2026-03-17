from __future__ import annotations

import logging
from pathlib import Path

from library_organizer_cli.progress import ProgressCallback

from .constants import SKIP_DIR_NAMES, is_media_file

logger = logging.getLogger(__name__)


def collect_media_paths(
    root: Path,
    mode: str,
    progress_callback: ProgressCallback,
    extra_skip_dir_names: set[str] | None = None,
) -> list[Path]:
    """
    Recursively collect media file paths under root, pruning SKIP_DIR_NAMES
    during traversal (case-insensitive directory names).
    mode: "scan" | "compare" | "duplicate" | "rename" | "organize" | "flatten" | "sync"...
    """
    files: list[Path] = []
    root = root.expanduser().resolve()
    if not root.is_dir():
        return files
    effective_skip = SKIP_DIR_NAMES
    if extra_skip_dir_names:
        effective_skip = effective_skip | {n.lower() for n in extra_skip_dir_names}

    try:
        for current_root, dir_names, file_names in root.walk(top_down=True):
            dir_names[:] = [
                name for name in dir_names if name.lower() not in effective_skip
            ]
            for file_name in file_names:
                file_path = current_root / file_name
                if not is_media_file(file_path):
                    continue
                files.append(file_path)
                progress_callback(
                    0, # 0 to leave the progress bar at the same position
                    1, # 1 to show the progress bar
                    "Discovering",
                    mode,
                    f"{file_path.as_posix()}"
                )
    except (OSError, PermissionError) as exc:
        logger.warning("Cannot walk under %s: %s", root, exc)
    return files
