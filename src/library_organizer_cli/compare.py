from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import xxhash

from .media_discovery import collect_media_paths
from .progress import ProgressCallback

logger = logging.getLogger(__name__)


def _full_hash(path: Path) -> tuple[Path, str] | None:
    """Compute a full xxh64 hash of a file in chunks."""
    hasher = xxhash.xxh64()
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                hasher.update(chunk)
        return path, hasher.hexdigest()
    except (OSError, PermissionError) as exc:
        logger.warning("Failed to hash %s: %s", path, exc)
        return None


def _hash_all(
    paths: Iterable[Path],
    label: str,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, list[Path]]:
    """Hash all files concurrently, reporting progress periodically."""
    file_list = list(paths)
    total = len(file_list)
    report = progress_callback or (lambda c, t, p, ph, f, fs, pb, tb: None)
    results: dict[str, list[Path]] = {}

    if total == 0:
        return results

    file_sizes: dict[Path, int | None] = {}
    total_bytes = 0
    for p in file_list:
        try:
            size = p.stat().st_size
        except OSError:
            size = None
        file_sizes[p] = size
        if size is not None:
            total_bytes += size

    processed_bytes = 0

    with ThreadPoolExecutor() as executor:
        future_to_path = {executor.submit(_full_hash, p): p for p in file_list}
        processed = 0
        for future in as_completed(future_to_path):
            result = future.result()
            processed += 1
            submitted_path = future_to_path[future]
            file_size_bytes = file_sizes.get(submitted_path)
            if file_size_bytes is not None:
                processed_bytes += file_size_bytes
            path_for_progress = (
                result[0].as_posix()
                if result is not None
                else submitted_path.as_posix()
            )
            if result is not None:
                path, digest = result
                results.setdefault(digest, []).append(path)
            if processed % 5 == 0 or processed == total:
                report(
                    processed,
                    total,
                    label,
                    f"{label.lower()}_hashing",
                    path_for_progress,
                    file_size_bytes,
                    processed_bytes,
                    total_bytes,
                )

    return results


def compare_folders(
    source: Path,
    target: Path,
    output_json: Path | str,
    progress_callback: ProgressCallback | None = None,
    *,
    extra_skip_dir_names: set[str] | None = None,
) -> dict:
    """Compare two folders by file content hash and write a JSON report."""
    output_path = Path(output_json).expanduser().resolve()

    source_files = collect_media_paths(
        source,
        "compare",
        progress_callback,
        extra_skip_dir_names=extra_skip_dir_names,
    )
    target_files = collect_media_paths(
        target,
        "compare",
        progress_callback,
        extra_skip_dir_names=extra_skip_dir_names,
    )

    source_hashes = _hash_all(source_files, "Source", progress_callback)
    target_hashes = _hash_all(target_files, "Target", progress_callback)

    source_keys = set(source_hashes.keys())
    target_keys = set(target_hashes.keys())

    matching_keys = source_keys & target_keys

    missing_in_target: list[dict[str, str]] = []
    for digest, paths in source_hashes.items():
        if digest in target_hashes:
            continue
        for p in paths:
            missing_in_target.append({"path": str(p), "hash": digest})

    missing_in_source: list[dict[str, str]] = []
    for digest, paths in target_hashes.items():
        if digest in source_hashes:
            continue
        for p in paths:
            missing_in_source.append({"path": str(p), "hash": digest})

    report = {
        "source_scanned": len(source_files),
        "target_scanned": len(target_files),
        "matching_files": len(matching_keys),
        "missing_in_target": missing_in_target,
        "missing_in_source": missing_in_source,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report

