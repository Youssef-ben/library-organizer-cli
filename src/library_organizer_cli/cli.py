from __future__ import annotations

import argparse

from . import __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan, find duplicates and organize a media library into a clean "
            "folder structure."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program version and exit.",
    )
    parser.add_argument(
        "source_root",
        help="Root folder to scan recursively.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying original files.",
    )
    parser.add_argument(
        "--name",
        default="file",
        metavar="FILE_NAME",
        help=(
            "Base filename for --mode rename (output looks like 'FILE_NAME (01).ext'). "
            "Default: file."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=(
            "all",
            "flatten",
            "organize",
            "find-duplicate",
            "compare",
            "sync",
            "delete-duplicate",
            "rename",
            "scan",
        ),
        default="all",
        help=(
            "Execution mode: 'all' (default) runs flatten then organize, "
            "'flatten' only flattens into a staging folder, "
            "'organize' organizes from an existing staging folder, "
            "'find-duplicate' runs the duplicate finder, "
            "'compare' compares two folders by content hash, "
            "'sync' copies missing files between source and target based on a compare "
            "report, 'delete-duplicate' deletes duplicate files based on a "
            "duplicates_results.json report, 'rename' renames files in the given "
            "folder (non-recursive) to '<name> (NN).ext' ordered by creation time, "
            "and 'scan' reports per-folder media file counts and sizes under source_root."
        ),
    )
    parser.add_argument(
        "--output",
        help=(
            "Path for the output report JSON. Used by find-duplicate, compare, sync, "
            "delete-duplicate, scan, and flatten modes. Defaults to a mode-specific "
            "filename in the current working directory if not provided (for scan: "
            "./results/scan_results.json, for flatten: ./results/flatten_results.json)."
        ),
    )
    parser.add_argument(
        "--target",
        help=(
            "Target folder to compare/sync against (required for --mode compare and --mode sync)."
        ),
    )
    parser.add_argument(
        "--output-folder",
        dest="output_folder",
        help=(
            "Override a default parent directory: for --mode flatten, flattened copies "
            "go to output_folder/staging (default when omitted: source_root/staging); "
            "for --mode organize and the organize stage of --mode all, the date-based "
            "layout is written under output_folder/organized (default when omitted: "
            "source_root/organized)."
        ),
    )
    parser.add_argument(
        "--direction",
        choices=("to-target", "to-source", "both"),
        help="Sync direction (required for --mode sync).",
    )
    parser.add_argument(
        "--input",
        help=(
            "Path to compare_results.json (used by --mode sync). "
            "Defaults to ./results/compare_results.json."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required when using --direction both without --dry-run.",
    )
    parser.add_argument(
        "--progress-format",
        choices=("text", "json"),
        default="text",
        help=(
            "Output format for progress: 'text' (default) for terminal progress bar, "
            " 'json' for one JSON object per line (e.g. for Electron/GUI)."
        ),
    )
    parser.add_argument(
        "--ignore-config",
        metavar="PATH",
        help=(
            "JSON file listing directory basenames to skip during recursive scans, "
            'e.g. {"folders": ["MyArchive", "exports"]}. Same rules as built-in '
            "skips (case-insensitive folder names). "
            "Default: ./results/ignored-folders.json in the current working directory."
        ),
    )
    args = parser.parse_args()

    if args.mode == "compare" and not args.target:
        parser.error("--target is required when using --mode compare")

    if args.mode == "sync" and not args.direction:
        parser.error("--direction is required when using --mode sync")
    if args.mode == "sync" and not args.target:
        parser.error("--target is required when using --mode sync")
    if (
        args.mode == "sync"
        and args.direction == "both"
        and not args.dry_run
        and not args.confirm
    ):
        parser.error("--confirm is required when using --direction both without --dry-run")

    return args
