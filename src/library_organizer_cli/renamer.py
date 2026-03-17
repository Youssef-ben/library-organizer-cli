from __future__ import annotations

import os
from pathlib import Path

from .progress import ProgressCallback


def _creation_time(stat: os.stat_result) -> float:
    """
    Cross-platform best-effort file creation time.

    Preference order: st_birthtime (macOS), then st_ctime (Windows: creation;
    Unix: metadata change time).
    """
    return getattr(stat, "st_birthtime", stat.st_ctime)


def rename_files(
    directory: Path | str,
    base_name: str = "file",
    *,
    verbose: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> int:
    """
    Rename each file in ``directory`` (non-recursive) to ``base_name (NN).ext``,
    ordered by creation time then modification time.

    Uses a two-phase rename to avoid collisions when reordering.

    Args:
        verbose: When False, suppress informational output (errors are still shown).
        progress_callback: Optional progress bar (same contract as other modes); when
            set, per-file success lines are omitted so output matches duplicate/compare.

    Returns:
        0 on success or if there is nothing to do, 1 on validation or rename error.
    """
    path = Path(directory).expanduser().resolve()

    if not path.is_dir():
        print(f"Error: {path} is not a valid directory.")
        return 1

    files = [f for f in path.iterdir() if f.is_file()]

    if not files:
        if verbose:
            print("No files to rename.")
        return 0

    file_data: list[tuple[Path, int, float, float]] = []
    for f in files:
        stat = f.stat()
        size_bytes = stat.st_size
        creation_time = _creation_time(stat)
        modified_time = stat.st_mtime
        file_data.append((f, size_bytes, creation_time, modified_time))

    # Order by creation time then modification time.
    file_data.sort(key=lambda x: (x[2], x[3]))

    report = progress_callback or (lambda *args: None)
    total = len(file_data)
    show_lines = verbose and progress_callback is None

    temp_files: list[tuple[Path, int]] = []
    for idx, (file_path, size_bytes, _, _) in enumerate(file_data):
        temp_name = path / f"__tmp__{idx}{file_path.suffix}"
        done = idx + 1
        try:
            file_path.rename(temp_name)
            temp_files.append((temp_name, size_bytes))
        except OSError as exc:
            print(f"Error: failed to rename {file_path.name} to temporary name: {exc}")
            return 1
        if done % 5 == 0 or done == total:
            report(
                done,
                total,
                "Pass 1    ",
                "rename_pass1",
                file_path.as_posix(),
                size_bytes,
                None,
                None,
            )

    padding = max(2, len(str(total)))
    exit_code = 0

    for idx, (temp_file, size_bytes) in enumerate(temp_files, start=1):
        new_name = f"{base_name} ({idx:0{padding}d}){temp_file.suffix}"
        final_path = path / new_name

        try:
            temp_file.rename(final_path)
            if show_lines:
                print(f"{temp_file.name} -> {new_name}")
        except OSError as exc:
            print(f"Error: failed to rename {temp_file.name} -> {new_name}: {exc}")
            exit_code = 1
        if idx % 5 == 0 or idx == total:
            report(
                idx,
                total,
                "Pass 2    ",
                "rename_pass2",
                temp_file.as_posix(),
                size_bytes,
                None,
                None,
            )

    return exit_code
