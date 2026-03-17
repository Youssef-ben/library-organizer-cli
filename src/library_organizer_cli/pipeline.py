from __future__ import annotations

import calendar
import errno
import json
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

from .compare import compare_folders
from .constants import is_media_file
from .duplicate import find_duplicates
from .extractor import configure_warning_log, get_true_date
from .ignore_config import default_ignored_folders_path, load_user_ignored_folder_names
from .media_discovery import collect_media_paths
from .progress import ProgressCallback, progress_callback_builder
from .renamer import rename_files
from .scan import format_bytes, scan_folders


def _pipeline_progress(args) -> ProgressCallback:
    return progress_callback_builder(args.progress_format)


def _user_extra_skip_dir_names(args) -> set[str]:
    path_str = getattr(args, "ignore_config", None)
    path = (
        Path(path_str).expanduser().resolve()
        if path_str
        else default_ignored_folders_path()
    )
    return load_user_ignored_folder_names(path)


def _merge_extra_skip_dir_names(
    base: set[str] | None,
    user: set[str],
) -> set[str] | None:
    merged: set[str] = set()
    if base:
        merged |= base
    merged |= user
    return merged if merged else None


def _emit_summary(args, json_payload: dict, text_emitter: Callable[[], None]) -> None:
    if args.progress_format == "json":
        print(json.dumps(json_payload), flush=True)
    else:
        text_emitter()


@dataclass
class StagedFile:
    source_path: Path
    staged_path: Path
    true_date: date


def _stage_source_files(
    source_root: Path,
    progress_callback: ProgressCallback,
    extra_skip_dir_names: set[str] | None = None,
) -> list[Path]:
    """Staging phase for flatten/all: discover source files."""
    return collect_media_paths(
        source_root,
        "staging",
        progress_callback,
        extra_skip_dir_names=extra_skip_dir_names,
    )


def _iter_temporary_files(temporary_dir: Path) -> list[Path]:
    """Returns files from an existing staging folder (non-recursive)."""
    if not temporary_dir.exists() or not temporary_dir.is_dir():
        return []
    files: list[Path] = []
    for path in temporary_dir.iterdir():
        if not path.is_file():
            continue
        if not is_media_file(path):
            continue
        files.append(path)
    return files


def _build_collision_safe_path(base_dir: Path, file_name: str) -> Path:
    """Ensures no file is overwritten by appending _1, _2, etc."""
    candidate = base_dir / file_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        candidate = base_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _flatten_to_temporary(
    source_files: Iterable[Path],
    temporary_dir: Path,
    dry_run: bool,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[StagedFile], list[str]]:
    """Flattening phase: copy staged source files into a flat staging folder."""
    staged_files: list[StagedFile] = []
    errors: list[str] = []
    files_list = list(source_files)
    total = len(files_list)
    report = progress_callback or (lambda *args: None)

    # Precompute byte totals for bytes/sec ETA (copy time is roughly proportional
    # to file size, which is a good approximation for most media files).
    file_sizes: dict[Path, int | None] = {}
    total_bytes = 0
    for sf in files_list:
        try:
            size = sf.stat().st_size
        except OSError:
            size = None
        file_sizes[sf] = size
        if size is not None:
            total_bytes += size

    processed_bytes = 0

    if not dry_run:
        if temporary_dir.exists():
            _rmtree_skip_errors(temporary_dir)
        temporary_dir.mkdir(parents=True, exist_ok=True)

    for i, source_file in enumerate(files_list, 1):
        try:
            file_date = get_true_date(source_file)
            staged_path = _build_collision_safe_path(temporary_dir, source_file.name)
            if not dry_run:
                shutil.copy2(source_file, staged_path)
            staged_files.append(StagedFile(source_file, staged_path, file_date))
        except Exception as exc:
            errors.append(f"[FLATTEN] {source_file.name}: {exc}")

        size_bytes = file_sizes.get(source_file)
        if size_bytes is not None:
            processed_bytes += size_bytes

        if i % 5 == 0 or i == total:
            report(
                i,
                total,
                "Flattening",
                "Copying",
                source_file.as_posix(),
                size_bytes,
                processed_bytes if not dry_run else None,
                total_bytes if not dry_run else None,
            )
    return staged_files, errors


def _stage_temporary_files(
    temporary_files: Iterable[Path],
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[StagedFile], list[str]]:
    """Builds staged metadata objects from already-flattened staging files."""
    staged_files: list[StagedFile] = []
    errors: list[str] = []
    files_list = list(temporary_files)
    total = len(files_list)
    report = progress_callback or (lambda c, t, p, ph, f: None)

    for i, temp_file in enumerate(files_list, 1):
        try:
            file_date = get_true_date(temp_file)
            staged_files.append(StagedFile(temp_file, temp_file, file_date))
        except Exception as exc:
            errors.append(f"[STAGE] {temp_file.name}: {exc}")
        if i % 5 == 0 or i == total:
            report(i, total, "Staging", "staging_from_staging", temp_file.as_posix())
    return staged_files, errors


def _organize_files(
    staged_files: Iterable[StagedFile],
    organized_dir: Path,
    dry_run: bool,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[Path], list[str]]:
    """Copies files from staging folder to YYYY/MM-Month folders."""
    copied_paths: list[Path] = []
    errors: list[str] = []
    items_list = list(staged_files)
    total = len(items_list)
    report = progress_callback or (lambda *args: None)

    file_sizes: dict[Path, int | None] = {}
    total_bytes = 0
    for item in items_list:
        try:
            size = item.staged_path.stat().st_size
        except OSError:
            size = None
        file_sizes[item.staged_path] = size
        if size is not None:
            total_bytes += size

    processed_bytes = 0

    for i, item in enumerate(items_list, 1):
        try:
            year_part = f"{item.true_date.year:04d}"
            month_num = item.true_date.month
            month_part = f"{month_num:02d}-{calendar.month_name[month_num]}"
            destination_dir = organized_dir / year_part / month_part
            destination_file = _build_collision_safe_path(
                destination_dir, item.staged_path.name
            )
            if not dry_run:
                destination_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.staged_path, destination_file)
            copied_paths.append(destination_file)
        except Exception as exc:
            errors.append(f"[ORGANIZE] {item.staged_path.name}: {exc}")

        size_bytes = file_sizes.get(item.staged_path)
        if size_bytes is not None:
            processed_bytes += size_bytes

        if i % 5 == 0 or i == total:
            report(
                i,
                total,
                "Organizing",
                "organizing_to_final",
                item.staged_path.as_posix(),
                size_bytes,
                processed_bytes if not dry_run else None,
                total_bytes if not dry_run else None,
            )
    return copied_paths, errors


def _verify_copy(staged_files: list[StagedFile], copied_paths: list[Path], dry_run: bool) -> bool:
    if dry_run:
        return True
    if len(staged_files) != len(copied_paths):
        return False
    return all(path.exists() and path.is_file() for path in copied_paths)


def _rmtree_skip_errors(path: Path) -> list[str]:
    """Remove a directory tree: chmod+retry for read-only, then skip other failures."""

    def _path_str(p: str | bytes) -> str:
        return os.fsdecode(p) if isinstance(p, bytes) else p

    def _can_try_chmod(exc: BaseException) -> bool:
        if isinstance(exc, PermissionError):
            return True
        if isinstance(exc, OSError):
            return exc.errno in (errno.EACCES, errno.EPERM)
        return False

    failed: list[str] = []

    def onexc(func, p: str | bytes, exc: BaseException) -> None:
        ps = _path_str(p)
        if _can_try_chmod(exc):
            try:
                os.chmod(ps, stat.S_IWRITE)
                func(p)
                return
            except OSError:
                pass
        failed.append(ps)

    shutil.rmtree(path, onexc=onexc)
    return failed


def _cleanup_temporary(
    temporary_dir: Path,
    should_cleanup: bool,
    dry_run: bool,
    progress_callback: ProgressCallback | None = None,
) -> tuple[bool, str]:
    if not should_cleanup:
        return False, "Skipped cleanup because verification failed."
    if dry_run:
        return True, "Dry run enabled: staging cleanup skipped."
    if temporary_dir.exists():
        path_str = temporary_dir.as_posix()
        if progress_callback:
            progress_callback(0, 1, "Cleanup", "Deleting staging", path_str)
        failed_paths = _rmtree_skip_errors(temporary_dir)
        if progress_callback:
            progress_callback(1, 1, "Cleanup", "Staging deleted", path_str)
        if failed_paths:
            n = len(failed_paths)
            return True, (
                f"Staging cleanup finished; {n} path(s) could not be deleted "
                "(permission denied, in use, or similar). The rest was removed."
            )

    return True, "Staging folder deleted."


def run_duplicate_pipeline(args) -> int:
    source_root = Path(args.source_root).expanduser().resolve()
    if not source_root.is_dir():
        print(f"Error: {source_root} is not a valid directory.")
        return 1

    candidate = source_root / "staging"
    scan_dir: Path = candidate if candidate.exists() and candidate.is_dir() else source_root

    if not scan_dir.exists() or not scan_dir.is_dir():
        print(f"Error: {scan_dir} is not a valid directory.")
        return 1

    dupe_output = (
        Path(args.output).expanduser().resolve()
        if getattr(args, "output", None)
        else Path.cwd() / "results" / "duplicates_results.json"
    )
    dupe_output.parent.mkdir(parents=True, exist_ok=True)

    progress_cb = _pipeline_progress(args)
    if args.progress_format == "text":
        print("--- Running duplicate finder ---")
        print(f"Scan directory : {scan_dir}")
        print(f"Output JSON    : {dupe_output}")
    user_skips = _user_extra_skip_dir_names(args)
    report = find_duplicates(
        scan_dir,
        dupe_output,
        progress_callback=progress_cb,
        extra_skip_dir_names=_merge_extra_skip_dir_names(None, user_skips),
    )

    def _text_duplicate_summary() -> None:
        print("\n--- Duplicate summary ---")
        print(f"Scanned files     : {report['scanned']}")
        print(f"Duplicate groups  : {report['duplicate_groups']}")
        print(f"Duplicate files   : {report['duplicate_files']}")
        print(f"Total size        : {format_bytes(report['total_bytes'])}")
        print(
            f"Duplicate size    : {format_bytes(report['duplicate_total_bytes'])}"
        )
        print(f"Report written to : {dupe_output}")

    _emit_summary(
        args,
        {
            "type": "summary",
            "action": "duplicate_finder",
            "scanned": report["scanned"],
            "duplicate_groups": report["duplicate_groups"],
            "duplicate_files": report["duplicate_files"],
            "total_bytes": report["total_bytes"],
            "duplicate_total_bytes": report["duplicate_total_bytes"],
            "report_path": str(dupe_output),
        },
        _text_duplicate_summary,
    )
    return 0


def run_rename_pipeline(args) -> int:
    source_root = Path(args.source_root).expanduser().resolve()
    if args.progress_format == "text":
        print("--- Rename files in folder ---")
        print(f"Directory : {source_root}")
        print(f"Base name : {args.name}")
    progress_cb = _pipeline_progress(args)
    verbose = args.progress_format == "text"
    code = rename_files(
        source_root,
        args.name,
        verbose=verbose,
        progress_callback=progress_cb,
    )
    _emit_summary(
        args,
        {
            "type": "summary",
            "action": "rename",
            "exit_code": code,
            "directory": str(source_root),
            "base_name": args.name,
        },
        lambda: None,
    )
    return code


def run_scan_pipeline(args) -> int:
    source_root = Path(args.source_root).expanduser().resolve()
    if not source_root.is_dir():
        print(f"Error: {source_root} is not a valid directory.")
        return 1

    output_json = (
        Path(args.output).expanduser().resolve()
        if getattr(args, "output", None)
        else Path.cwd() / "results" / "scan_results.json"
    )

    progress_cb = _pipeline_progress(args)
    if args.progress_format == "text":
        print("--- Scan library ---")
        print(f"Source root   : {source_root}")
        print(f"Output JSON   : {output_json}")

    user_skips = _user_extra_skip_dir_names(args)
    report = scan_folders(
        source_root,
        progress_callback=progress_cb,
        extra_skip_dir_names=_merge_extra_skip_dir_names(None, user_skips),
    )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    def _text_scan_summary() -> None:
        print("\n--- Scan summary ---")
        print(f"Total folders   : {report['folder_count']}")
        print(f"Total files     : {report['total_files']}")
        print(f"Total size      : {format_bytes(report['total_bytes'])}")
        print("\nPer-folder (relative path, direct files, recursive size):")
        for entry in report["folders"]:
            rel = entry["path"] if entry["path"] else "."
            print(
                f"  {rel:50}  {entry['direct_files']:4}  {format_bytes(entry['recursive_bytes'])}"
            )
        print(f"\nReport written to : {output_json}")

    _emit_summary(
        args,
        {
            "type": "summary",
            "action": "scan",
            "total_files": report["total_files"],
            "total_bytes": report["total_bytes"],
            "folder_count": report["folder_count"],
            "report_path": str(output_json),
        },
        _text_scan_summary,
    )

    return 0


def run_compare_pipeline(args) -> int:
    source = Path(args.source_root).expanduser().resolve()
    target = Path(args.target).expanduser().resolve()

    if not source.is_dir():
        print(f"Error: {source} is not a valid directory.")
        return 1
    if not target.is_dir():
        print(f"Error: {target} is not a valid directory.")
        return 1

    output = (
        Path(args.output).expanduser().resolve()
        if getattr(args, "output", None)
        else Path.cwd() / "results" / "compare_results.json"
    )

    progress_cb = _pipeline_progress(args)

    output.parent.mkdir(parents=True, exist_ok=True)
    user_skips = _user_extra_skip_dir_names(args)
    report = compare_folders(
        source,
        target,
        output,
        progress_callback=progress_cb,
        extra_skip_dir_names=_merge_extra_skip_dir_names(None, user_skips),
    )

    missing_in_target_count = len(report.get("missing_in_target", []))
    missing_in_source_count = len(report.get("missing_in_source", []))

    def _text_compare_summary() -> None:
        print("\n--- Compare summary ---")
        print(f"Source scanned      : {report.get('source_scanned', 0)}")
        print(f"Target scanned      : {report.get('target_scanned', 0)}")
        print(f"Matching files      : {report.get('matching_files', 0)}")
        print(f"Missing in target   : {missing_in_target_count}")
        print(f"Missing in source   : {missing_in_source_count}")
        print(f"Report written to   : {output}")

    _emit_summary(
        args,
        {
            "type": "summary",
            "action": "compare",
            "source_scanned": report.get("source_scanned", 0),
            "target_scanned": report.get("target_scanned", 0),
            "matching_files": report.get("matching_files", 0),
            "missing_in_target": missing_in_target_count,
            "missing_in_source": missing_in_source_count,
            "report_path": str(output),
        },
        _text_compare_summary,
    )

    return 0


def run_sync_pipeline(args) -> int:
    # Local import to avoid circular dependency:
    # sync.py imports _build_collision_safe_path from pipeline.py,
    # so a top-level import here would create a cycle.
    from .sync import run_sync

    source_root = Path(args.source_root).expanduser().resolve()
    target_root = Path(args.target).expanduser().resolve()

    if not source_root.is_dir():
        print(f"Error: {source_root} is not a valid directory.")
        return 1
    if not target_root.is_dir():
        print(f"Error: {target_root} is not a valid directory.")
        return 1

    input_json = (
        Path(args.input).expanduser().resolve()
        if getattr(args, "input", None)
        else Path.cwd() / "results" / "compare_results.json"
    )
    if not input_json.exists():
        print(f"Error: Compare report not found: {input_json}")
        return 1

    output = (
        Path(args.output).expanduser().resolve()
        if getattr(args, "output", None)
        else Path.cwd() / "results" / "sync_results.json"
    )

    log_path = configure_warning_log()
    # Append a simple header so the log file is non-empty even if no warnings occur.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header_lines = [
        "##########################################",
        f"Log: {log_path.name}",
        "Action: Sync",
        f"Args: mode={args.mode}, direction={args.direction}",
        "##########################################",
        "",
    ]
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(header_lines))
    progress_cb = _pipeline_progress(args)

    report = run_sync(
        source_root=source_root,
        target_root=target_root,
        input_json=input_json,
        direction=args.direction,
        dry_run=args.dry_run,
        progress_callback=progress_cb,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    has_errors = (report.get("to_target_errors", 0) or 0) > 0 or (
        report.get("to_source_errors", 0) or 0
    ) > 0

    def _text_sync_summary() -> None:
        print("\n--- Sync summary ---")
        print(f"Direction           : {report.get('direction')}")
        print(f"To-target copied    : {report.get('to_target_copied', 0)}")
        print(f"To-target errors    : {report.get('to_target_errors', 0)}")
        print(f"To-source copied    : {report.get('to_source_copied', 0)}")
        print(f"To-source errors    : {report.get('to_source_errors', 0)}")
        print(f"Report written to   : {output}")
        print(f"Log path            : {log_path.resolve()}")

    _emit_summary(
        args,
        {
            "type": "summary",
            "action": "sync",
            "direction": report.get("direction"),
            "to_target_copied": report.get("to_target_copied", 0),
            "to_target_errors": report.get("to_target_errors", 0),
            "to_source_copied": report.get("to_source_copied", 0),
            "to_source_errors": report.get("to_source_errors", 0),
            "report_path": str(output),
        },
        _text_sync_summary,
    )

    return 2 if has_errors else 0


def run_organize_pipeline(args) -> int:
    source_root = Path(args.source_root).expanduser().resolve()
    if not source_root.is_dir():
        print(f"Error: {source_root} is not a valid directory.")
        return 1

    log_path = configure_warning_log()
    action = "File Organizer"

    log_path.parent.mkdir(parents=True, exist_ok=True)
    header_lines = [
        "##########################################",
        f"Log: {log_path.name}",
        f"Action: {action}",
        f"Args: mode={args.mode}",
        "##########################################",
        "",
    ]
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(header_lines))

    mode = args.mode
    temp_dir = source_root / "staging"
    org_dir = source_root / "organized"
    if mode == "flatten" and getattr(args, "output_folder", None):
        temp_dir = Path(args.output_folder).expanduser().resolve() / "staging"
    elif getattr(args, "output_folder", None):
        org_dir = Path(args.output_folder).expanduser().resolve() / "organized"

    extra_skip_dir_names: set[str] | None = None
    # In `--mode all` / `--mode flatten` we scan source_root during flattening. If
    # the staging folder and/or organize target live inside source_root and use a
    # name not already in SKIP_DIR_NAMES, we must prune them to avoid re-discovering
    # output we are producing.
    if mode in {"all", "flatten"}:
        extras: set[str] = set()
        try:
            temp_dir.relative_to(source_root)
            extras.add(temp_dir.name.lower())
        except ValueError:
            pass
        if mode == "all":
            try:
                org_dir.relative_to(source_root)
                extras.add(org_dir.name.lower())
            except ValueError:
                pass
        extra_skip_dir_names = extras if extras else None
        extra_skip_dir_names = _merge_extra_skip_dir_names(
            extra_skip_dir_names,
            _user_extra_skip_dir_names(args),
        )

    flatten_output_json: Path | None = None
    if mode == "flatten":
        flatten_output_json = (
            Path(args.output).expanduser().resolve()
            if getattr(args, "output", None)
            else Path.cwd() / "results" / "flatten_results.json"
        )

    source_files: list[Path] = []
    staged: list[StagedFile] = []
    final_paths: list[Path] = []
    s_errs: list[str] = []
    o_errs: list[str] = []
    is_verified = True
    cleaned = False
    cleanup_message = "Not applicable for selected mode."

    progress_cb = _pipeline_progress(args)

    if mode in {"all", "flatten"}:
        # Staging phase (source): discover files
        source_files = _stage_source_files(
            source_root,
            progress_cb,
            extra_skip_dir_names=extra_skip_dir_names,
        )
        if not source_files:
            print("No files found to process.")
            if mode != "flatten":
                return 0
        else:
            if args.progress_format == "text":
                print(
                    f"--- Staging from source: {len(source_files)} files discovered "
                    f"(mode: {mode}) ---"
                )
            # Show staging progress bar for source files
            total_staging = len(source_files)
            if total_staging > 0:
                for i, _ in enumerate(source_files, 1):
                    if i % 5 == 0 or i == total_staging:
                        progress_cb(
                            i,
                            total_staging,
                            "Staging",
                            "Scanning",
                            source_files[i - 1].as_posix(),
                        )
            # Flattening phase: copy into staging
            staged, s_errs = _flatten_to_temporary(
                source_files, temp_dir, args.dry_run, progress_callback=progress_cb
            )

    if mode == "flatten":
        cleanup_message = "Skipped cleanup in flatten mode."
    elif mode == "organize":
        temporary_files = _iter_temporary_files(temp_dir)
        if not temporary_files:
            print(f"Error: Staging folder is missing or empty: {temp_dir}")
            return 1
        if args.progress_format == "text":
            print(
                f"--- Staging from staging: {len(temporary_files)} files discovered "
                f"(mode: {mode}) ---"
            )
        # Staging-from-temp phase
        staged, s_errs = _stage_temporary_files(temporary_files, progress_callback=progress_cb)
        # Organizing phase
        final_paths, o_errs = _organize_files(
            staged,
            org_dir,
            args.dry_run,
            progress_callback=progress_cb,
        )
        is_verified = _verify_copy(staged, final_paths, args.dry_run)
        cleaned, cleanup_message = _cleanup_temporary(
            temp_dir, is_verified, args.dry_run, progress_callback=progress_cb
        )
    else:
        final_paths, o_errs = _organize_files(
            staged,
            org_dir,
            args.dry_run,
            progress_callback=progress_cb,
        )
        is_verified = _verify_copy(staged, final_paths, args.dry_run)
        cleaned, cleanup_message = _cleanup_temporary(
            temp_dir, is_verified, args.dry_run, progress_callback=progress_cb
        )

    if mode == "flatten" and flatten_output_json is not None:
        total_scanned = len(source_files)
        total_staged = len(staged)
        total_bytes = 0
        for sf in staged:
            try:
                total_bytes += sf.source_path.stat().st_size
            except (OSError, PermissionError):
                # If a file disappears/unreadable between discovery and reporting,
                # we still return a report with best-effort totals.
                pass

        report = {
            "root": source_root.as_posix(),
            "results": temp_dir.as_posix(),
            "total_scanned": total_scanned,
            "total_staged": total_staged,
            "total_bytes": total_bytes,
        }

        flatten_output_json.parent.mkdir(parents=True, exist_ok=True)
        with flatten_output_json.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    summary: dict = {
        "type": "summary",
        "action": "organize",
        "mode": mode,
        "scanned": len(source_files),
        "staged": len(staged),
        "organized": len(final_paths),
        "errors": len(s_errs) + len(o_errs),
        "verified": is_verified,
        "cleanup_done": cleaned,
        "cleanup_message": cleanup_message,
        "log_path": str(log_path.resolve()),
    }
    if mode == "flatten" and flatten_output_json is not None:
        summary["report_path"] = str(flatten_output_json)

    def _text_organize_summary() -> None:
        print("\n--- Summary ---")
        print(f"Mode: {mode}")
        print(f"Total Scanned:  {len(source_files)}")
        print(f"Total Staged: {len(staged)}")
        print(f"Successfully Organized: {len(final_paths)}")
        print(f"Errors Encountered:    {len(s_errs) + len(o_errs)}")
        print(f"Verified: {is_verified}")
        print(f"Cleanup: {cleanup_message}")
        print(f"Cleanup Done: {cleaned}")
        if mode == "flatten" and flatten_output_json is not None:
            print(f"Report written to   : {flatten_output_json}")
        if s_errs or o_errs:
            print(f"Check logs for details: {log_path.resolve()}")

    _emit_summary(args, summary, _text_organize_summary)

    if not is_verified and not args.dry_run:
        print("Warning: Verification failed. Some files may not have moved correctly.")
        return 2

    return 0


def _is_within_root(root: Path, path: Path) -> bool:
    """Return True if path is a descendant of root (safety check)."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def run_delete_duplicates_pipeline(args) -> int:
    source_root = Path(args.source_root).expanduser().resolve()
    if not source_root.is_dir():
        print(f"Error: {source_root} is not a valid directory.")
        return 1

    input_json = (
        Path(args.input).expanduser().resolve()
        if getattr(args, "input", None)
        else Path.cwd() / "results" / "duplicates_results.json"
    )
    if not input_json.exists():
        print(f"Error: Duplicate report not found: {input_json}")
        return 1

    output = (
        Path(args.output).expanduser().resolve()
        if getattr(args, "output", None)
        else Path.cwd() / "results" / "delete_results.json"
    )

    log_path = configure_warning_log()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header_lines = [
        "##########################################",
        f"Log: {log_path.name}",
        "Action: Delete duplicates",
        f"Args: mode={args.mode}, dry_run={args.dry_run}, input={input_json}",
        "##########################################",
        "",
    ]
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(header_lines))

    try:
        with input_json.open("r", encoding="utf-8") as f:
            report = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Error: Failed to parse duplicate report {input_json}: {exc}")
        return 1

    candidate_paths: list[Path] = []
    # The 'delete' format is produced by an external tool (e.g. the Electron UI),
    # which allows the user to select a subset of duplicates before deletion.
    # Format: {"delete": {"files": ["path/to/file1", ...], "count": N}}
    # If this key is absent, fall back to the standard duplicates_results.json format.
    delete_obj = report.get("delete")
    delete_format_valid = isinstance(delete_obj, dict) and isinstance(
        delete_obj.get("files"), list
    )
    if delete_format_valid:
        files_list = delete_obj["files"]
        for item in files_list:
            if isinstance(item, str) and item.strip():
                candidate_paths.append(Path(item).expanduser())
        if "count" in delete_obj and delete_obj["count"] != len(files_list):
            with log_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"[WARN] delete.count ({delete_obj['count']}) != len(files) "
                    f"({len(files_list)}). Using len(files).\n"
                )
    else:
        groups = report.get("groups")
        if isinstance(groups, list):
            for group in groups:
                files = group.get("files") if isinstance(group, dict) else None
                if not isinstance(files, list) or len(files) <= 1:
                    continue
                for entry in files[1:]:
                    if not isinstance(entry, dict):
                        continue
                    path_str = entry.get("path")
                    if isinstance(path_str, str):
                        candidate_paths.append(Path(path_str).expanduser())
        else:
            print(
                "Error: Input must be a delete list (top-level 'delete' with 'files' "
                "array) or a duplicates report ('groups' array)."
            )
            return 1

    seen_resolved: set[Path] = set()
    deduped: list[Path] = []
    for p in candidate_paths:
        try:
            r = p.resolve()
        except (OSError, RuntimeError):
            continue
        if r not in seen_resolved:
            seen_resolved.add(r)
            deduped.append(p)
    candidate_paths = deduped

    total_candidates = len(candidate_paths)
    requested = total_candidates
    deleted = 0
    missing = 0
    skipped = 0
    errors = 0

    progress_cb = _pipeline_progress(args)

    for idx, raw_path in enumerate(candidate_paths, start=1):
        resolved = raw_path.resolve()
        size_bytes: int | None = None
        try:
            if resolved.exists() and resolved.is_file():
                size_bytes = resolved.stat().st_size
        except OSError:
            size_bytes = None
        if not _is_within_root(source_root, resolved):
            skipped += 1
            with log_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"[SKIP] {resolved} is outside source_root {source_root}. "
                    "Skipping deletion.\n"
                )
            if idx % 5 == 0 or idx == total_candidates:
                progress_cb(
                    idx,
                    total_candidates,
                    "Deleting",
                    "delete_duplicates",
                    resolved.as_posix(),
                    size_bytes,
                    None,
                    None,
                )
            continue

        if not resolved.exists():
            missing += 1
            if idx % 5 == 0 or idx == total_candidates:
                progress_cb(
                    idx,
                    total_candidates,
                    "Deleting",
                    "delete_duplicates",
                    resolved.as_posix(),
                    size_bytes,
                    None,
                    None,
                )
            continue

        if args.dry_run:
            deleted += 1  # count what would be deleted
            if idx % 5 == 0 or idx == total_candidates:
                progress_cb(
                    idx,
                    total_candidates,
                    "Deleting",
                    "delete_duplicates",
                    resolved.as_posix(),
                    size_bytes,
                    None,
                    None,
                )
            continue

        try:
            resolved.unlink()
            deleted += 1
        except OSError as exc:
            errors += 1
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"[ERROR] Failed to delete {resolved}: {exc}\n")
        if idx % 5 == 0 or idx == total_candidates:
            progress_cb(
                idx,
                total_candidates,
                "Deleting",
                "delete_duplicates",
                resolved.as_posix(),
                size_bytes,
                None,
                None,
            )

    summary = {
        "requested": requested,
        "deleted": deleted,
        "missing": missing,
        "skipped": skipped,
        "errors": errors,
        "dry_run": bool(args.dry_run),
        "source_root": str(source_root),
        "input_path": str(input_json),
        "log_path": str(log_path.resolve()),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    def _text_delete_summary() -> None:
        print("\n--- Delete-duplicate summary ---")
        print(f"Requested deletions : {requested}")
        print(f"Deleted files       : {deleted}")
        print(f"Missing files       : {missing}")
        print(f"Skipped (outside root) : {skipped}")
        print(f"Errors              : {errors}")
        print(f"Dry run             : {bool(args.dry_run)}")
        print(f"Report written to   : {output}")
        print(f"Log path            : {log_path.resolve()}")

    _emit_summary(
        args,
        {
            "type": "summary",
            "action": "delete-duplicate",
            "requested": requested,
            "deleted": deleted,
            "missing": missing,
            "skipped": skipped,
            "errors": errors,
            "dry_run": bool(args.dry_run),
            "report_path": str(output),
        },
        _text_delete_summary,
    )

    return 2 if errors > 0 else 0

