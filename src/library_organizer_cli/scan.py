from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from .media_discovery import collect_media_paths
from .progress import ProgressCallback

logger = logging.getLogger(__name__)


def scan_folders(
    root: Path,
    *,
    progress_callback: ProgressCallback | None = None,
    extra_skip_dir_names: set[str] | None = None,
) -> dict:
    """
    Scan media files under root; aggregate per-folder direct file counts and
    recursive byte totals. Progress is reported during the stat pass.
    """
    root = root.expanduser().resolve()
    report = progress_callback or (lambda *args: None)
    paths = collect_media_paths(
        root,
        "scan",
        report,
        extra_skip_dir_names=extra_skip_dir_names,
    )

    total_paths = len(paths)

    direct: dict[Path, int] = defaultdict(int)
    recursive: dict[Path, int] = defaultdict(int)
    stat_infos: list[tuple[Path, int | None, Path | None]] = []
    total_bytes = 0
    total_files = 0

    # First pass: stat files once so we can compute total_bytes before emitting
    # progress ticks (required for byte-based ETA).
    for path in paths:
        try:
            st = path.stat()
            size = st.st_size
            parent = path.parent
            stat_infos.append((path, size, parent))
            total_bytes += size
            total_files += 1
        except OSError as exc:
            logger.warning("Skipping stat %s: %s", path, exc)
            stat_infos.append((path, None, None))

    processed_bytes = 0

    # Second pass: aggregate per-folder totals and emit progress.
    for i, (path, size, parent) in enumerate(stat_infos, 1):
        if size is not None and parent is not None:
            processed_bytes += size
            direct[parent] += 1

            cur = parent
            while True:
                recursive[cur] += size
                if cur == root:
                    break
                cur = cur.parent

        if i % 5 == 0 or i == total_paths:
            report(
                i,
                total_paths,
                "Scanning  ",
                "scan",
                path.as_posix(),
                size,
                processed_bytes,
                total_bytes,
            )

    all_dirs = set(direct.keys()) | set(recursive.keys())

    def _rel_posix(d: Path) -> str:
        if d == root:
            return ""
        return d.relative_to(root).as_posix()

    folder_rows = []
    for d in sorted(all_dirs, key=lambda p: _rel_posix(p)):
        folder_rows.append(
            {
                "path": _rel_posix(d),
                "direct_files": direct.get(d, 0),
                "recursive_bytes": recursive.get(d, 0),
            }
        )

    return {
        "root": root.as_posix(),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "folder_count": len(all_dirs),
        "folders": folder_rows,
    }


def format_bytes(n: int) -> str:
    """Human-readable byte size for terminal output."""
    if n < 0:
        n = 0
    if n < 1024:
        return f"{n} B"
    value = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}"
    return f"{n} B"
