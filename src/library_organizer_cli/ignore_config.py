from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

IGNORED_FOLDERS_JSON_NAME = "ignored-folders.json"


def default_ignored_folders_path(cwd: Path | None = None) -> Path:
    """Path to the user ignore list under ``cwd`` (default: current working directory)."""
    base = cwd if cwd is not None else Path.cwd()
    return (base / "results" / IGNORED_FOLDERS_JSON_NAME).resolve()


def load_user_ignored_folder_names(path: Path) -> set[str]:
    """
    Load optional ``{"folders": ["name", ...]}`` from ``path``.
    Each name is a directory basename, compared case-insensitively like SKIP_DIR_NAMES.
    Missing file returns an empty set. Invalid JSON or wrong shape logs a warning.
    """
    path = path.expanduser().resolve()
    if not path.is_file():
        return set()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Cannot read ignored folders config %s: %s", path, exc)
        return set()

    if not isinstance(data, dict):
        logger.warning("Ignored folders config %s: expected JSON object", path)
        return set()
    folders = data.get("folders")
    if not isinstance(folders, list):
        logger.warning(
            "Ignored folders config %s: missing or invalid \"folders\" array",
            path,
        )
        return set()

    names: set[str] = set()
    for item in folders:
        if isinstance(item, str):
            names.add(item.lower())
        else:
            logger.warning(
                "Ignored folders config %s: skipping non-string entry %r",
                path,
                item,
            )
    return names
