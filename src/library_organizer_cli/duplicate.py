from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import xxhash

from .media_discovery import collect_media_paths
from .progress import ProgressCallback

logger = logging.getLogger(__name__)


SHADOW_READ_BYTES = 64 * 1024
FULL_HASH_CHUNK_BYTES = 8 * 1024


@dataclass
class FileEntry:
    """Internal entry for a scanned file."""

    path: Path
    size_bytes: int
    modified: datetime


def _parse_suffix(path: Path) -> tuple[str, int | None]:
    """
    Split a filename stem into (base, suffix_number_or_None).

    Examples:
    - photo.jpg        -> ("photo", None)
    - photo_1.jpg      -> ("photo", 1)
    - holiday_2024.jpg -> ("holiday_2024", None)  # last part not numeric
    """
    stem = path.stem
    base, sep, tail = stem.rpartition("_")
    if sep and tail.isdigit():
        return base, int(tail)
    return stem, None


def _order_group(entries: list[FileEntry]) -> list[FileEntry]:
    """
    Order a duplicate group so that:
    - First file is the best candidate for the 'original':
      * Prefer names without a numeric _N suffix.
      * Among those, pick the oldest modified time; ties by path.
    - Remaining files follow, ordered by:
      * suffix number ascending when present,
      * then modified time ascending,
      * then path lexicographically.
    """
    if not entries:
        return entries

    def main_key(entry: FileEntry) -> tuple[int, datetime, str]:
        _, suffix_num = _parse_suffix(entry.path)
        no_suffix_flag = 0 if suffix_num is None else 1
        return (no_suffix_flag, entry.modified, entry.path.as_posix())

    def rest_key(entry: FileEntry) -> tuple[int, int, datetime, str]:
        _, suffix_num = _parse_suffix(entry.path)
        has_suffix_flag = 0 if suffix_num is not None else 1
        num = suffix_num if suffix_num is not None else 0
        return (has_suffix_flag, num, entry.modified, entry.path.as_posix())

    main_entry = min(entries, key=main_key)
    remaining = [e for e in entries if e is not main_entry]
    remaining_sorted = sorted(remaining, key=rest_key)
    return [main_entry, *remaining_sorted]


def _pass1_partial_hash(path: Path) -> tuple[str, FileEntry] | None:
    """Read first 64KB, compute xxh64; return (partial_hash_hex, FileEntry) or None on error."""
    try:
        stat = path.stat()
        with path.open("rb") as f:
            data = f.read(SHADOW_READ_BYTES)
        partial_hash = xxhash.xxh64(data).hexdigest()
        entry = FileEntry(
            path=path,
            size_bytes=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime),
        )
        return (partial_hash, entry)
    except (OSError, PermissionError) as exc:
        logger.warning("Pass 1 skip %s: %s", path, exc)
        return None


def _pass2_full_hash(entry: FileEntry) -> tuple[str, FileEntry] | None:
    """Full file hash in 8KB chunks; return (full_hash_hex, entry) or None on error."""
    try:
        hasher = xxhash.xxh64()
        with entry.path.open("rb") as f:
            while True:
                chunk = f.read(FULL_HASH_CHUNK_BYTES)
                if not chunk:
                    break
                hasher.update(chunk)
        return (hasher.hexdigest(), entry)
    except (OSError, PermissionError) as exc:
        logger.warning("Pass 2 skip %s: %s", entry.path, exc)
        return None


def find_duplicates(
    temporary_dir: Path,
    output_json: Path,
    progress_callback: ProgressCallback | None = None,
    *,
    extra_skip_dir_names: set[str] | None = None,
) -> dict:
    """
    Scan directory for duplicate files (two-pass: partial then full hash).
    Writes report to output_json and returns the same dict.
    """
    progress_report = progress_callback or (lambda *args: None)
    paths = collect_media_paths(
        temporary_dir,
        "duplicate",
        progress_report,
        extra_skip_dir_names=extra_skip_dir_names,
    )
    total_files = len(paths)
    total_bytes = 0
    for p in paths:
        try:
            total_bytes += p.stat().st_size
        except OSError as exc:
            logger.warning("Stat skip %s: %s", p, exc)

    # Byte ETA for pass_1: we only read SHADOW_READ_BYTES per file.
    file_size_bytes_pass1: dict[Path, int | None] = {}
    shadow_bytes_pass1: dict[Path, int | None] = {}
    total_bytes_pass1 = 0
    for p in paths:
        try:
            size = p.stat().st_size
        except OSError:
            size = None
        file_size_bytes_pass1[p] = size
        if size is None:
            shadow_bytes_pass1[p] = None
            continue
        shadow = min(size, SHADOW_READ_BYTES)
        shadow_bytes_pass1[p] = shadow
        total_bytes_pass1 += shadow

    # Synthetic pre-pass "scanning" progress: keep byte ETA fields unset.
    for i in range(1, total_files + 1):
        if i % 5 == 0 or i == total_files:
            progress_report(
                i,
                total_files,
                "Scanning  ",
                "scanning",
                paths[i - 1].as_posix(),
                None,
                None,
                None,
            )

    partial_groups: dict[str, list[FileEntry]] = {}
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(_pass1_partial_hash, p): p for p in paths}
        done = 0
        processed_bytes_pass1 = 0
        for future in as_completed(futures):
            result = future.result()
            done += 1
            submitted_path = futures[future]
            file_size_bytes = file_size_bytes_pass1.get(submitted_path)
            shadow_bytes = shadow_bytes_pass1.get(submitted_path)
            if shadow_bytes is not None:
                processed_bytes_pass1 += shadow_bytes
            path_p1 = (
                result[1].path.as_posix()
                if result is not None
                else submitted_path.as_posix()
            )
            if done % 5 == 0 or done == total_files:
                progress_report(
                    done,
                    total_files,
                    "Pass 1    ",
                    "pass_1",
                    path_p1,
                    file_size_bytes,
                    processed_bytes_pass1,
                    total_bytes_pass1,
                )
            if result is None:
                continue
            partial_hash, entry = result
            partial_groups.setdefault(partial_hash, []).append(entry)

    candidates: list[FileEntry] = []
    for entries in partial_groups.values():
        if len(entries) > 1:
            candidates.extend(entries)
    total_candidates = len(candidates)

    full_groups: dict[str, list[FileEntry]] = {}
    if total_candidates > 0:
        total_bytes_pass2 = sum(e.size_bytes for e in candidates)
        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(_pass2_full_hash, entry): entry for entry in candidates}
            done = 0
            processed_bytes_pass2 = 0
            for future in as_completed(futures):
                result = future.result()
                done += 1
                submitted_entry = futures[future]
                file_size_bytes = submitted_entry.size_bytes
                processed_bytes_pass2 += file_size_bytes
                path_p2 = (
                    result[1].path.as_posix()
                    if result is not None
                    else submitted_entry.path.as_posix()
                )
                if done % 5 == 0 or done == total_candidates:
                    progress_report(
                        done,
                        total_candidates,
                        "Pass 2    ",
                        "pass_2",
                        path_p2,
                        file_size_bytes,
                        processed_bytes_pass2,
                        total_bytes_pass2,
                    )
                if result is None:
                    continue
                full_hash, entry = result
                full_groups.setdefault(full_hash, []).append(entry)

    duplicate_groups_list = []
    for h, entries in full_groups.items():
        if len(entries) > 1:
            ordered = _order_group(entries)
            duplicate_groups_list.append((h, ordered))
    duplicate_files_count = sum(len(entries) for _, entries in duplicate_groups_list)
    duplicate_total_bytes = sum(
        e.size_bytes for _, entries in duplicate_groups_list for e in entries
    )

    groups_payload = [
        {
            "hash": h,
            "files": [
                {
                    "path": e.path.as_posix(),
                    "size_bytes": e.size_bytes,
                    "modified": e.modified.isoformat(),
                }
                for e in entries
            ],
        }
        for h, entries in duplicate_groups_list
    ]

    report = {
        "scanned": total_files,
        "duplicate_groups": len(duplicate_groups_list),
        "duplicate_files": duplicate_files_count,
        "total_bytes": total_bytes,
        "duplicate_total_bytes": duplicate_total_bytes,
        "groups": groups_payload,
    }

    progress_report(
        1,
        1,
        "Writing   ",
        "writing",
        output_json.as_posix(),
        None,
        None,
        None,
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report
