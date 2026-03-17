# Library Organizer CLI

Library Organizer CLI is a desktop utility that helps you scan, catalog, and manage your local photo and video library in a structured way. It automates the process of discovering media files from your filesystem, extracting and normalizing metadata (including EXIF where available), and generating an organized, searchable catalog that you can browse or export for backup and sharing. It also detects potential duplicate files based on content hashes so you can safely clean up redundant copies.

## Key features

- **Scan photo and video folders**: Recursively walk one or more root folders to discover supported media files.
- **Extract metadata**: Read filesystem attributes and EXIF data (when present) to capture dates, dimensions, camera/device details, and more.
- **Detect duplicate files**: Use robust content hashing to flag likely duplicates, even when filenames differ.
- **Build an organized catalog**: Normalize and structure metadata so your library is easier to search, filter, and reason about.
- **Exportable results**: Produce a machine-friendly catalog that can be inspected, backed up, or used by other tools.

## Installation

- **Prerequisites**:
  - Python **3.12+** installed and available on your `PATH`.
  - Git (if you are installing from source).
- **From source (recommended for now)**:
  1. Clone the repository: `git clone <this-repo-url> && cd library-organizer-cli`
  2. Initialize the project (creates `.venv` and installs dependencies in editable mode): `bash scripts/initialize.sh`
  3. Activate the virtual environment:
     - On Windows (Git Bash / WSL): `source .venv/Scripts/activate`
     - On Linux/macOS: `source .venv/bin/activate`
  4. Run the CLI: `library-organizer-cli --help`
- **Build a standalone executable (optional)**:
  - After initialization and with the virtual environment active, run: `bash scripts/build.sh`
  - The packaged executable will be available under the `dist/` directory as `library-organizer-cli`.

## Quick start

Once installed (and with your virtual environment activated, if using one), you can:

1. **Run a full organize pass** (flatten + organize) on a library:
   - `library-organizer-cli /path/to/your/photos`
2. **Preview changes without touching files**:
   - `library-organizer-cli /path/to/your/photos --dry-run`
3. **Only organize from an already-prepared staging folder**:
   - `library-organizer-cli /path/to/temp --mode organize`
4. **Only flatten into a staging folder** (no final organization yet):
   - `library-organizer-cli /path/to/your/photos --mode flatten`
   - Custom flatten base directory (flattened files go in `output_folder/staging`; default is `source_root/staging`):  
     `library-organizer-cli /path/to/your/photos --mode flatten --output-folder /path/to/library/root`
5. **Find duplicate media files and write a JSON report**:
   - `library-organizer-cli /path/to/your/photos --mode find-duplicate --output duplicates_results.json`
6. **Compare two folders by content (hash-based)**:
   - `library-organizer-cli /path/to/source --mode compare --target /path/to/target --output compare_results.json`
7. **Sync missing files between two folders based on a previous compare report**:
   - First generate a report:  
     - `library-organizer-cli /path/to/source --mode compare --target /path/to/target --output compare_results.json`
   - Then run a dry-run sync (preview only):  
     - `library-organizer-cli /path/to/source --mode sync --target /path/to/target --direction to-target --dry-run`
   - Finally, perform the actual sync once satisfied with the preview:  
     - `library-organizer-cli /path/to/source --mode sync --target /path/to/target --direction to-target`
8. **Delete duplicate files** (based on a duplicate report):
   - First generate a duplicate report:  
     - `library-organizer-cli /path/to/your/photos --mode find-duplicate --output duplicates_results.json`
   - Preview which files would be deleted (dry-run):  
     - `library-organizer-cli /path/to/your/photos --mode delete-duplicate --input duplicates_results.json --dry-run`
   - Run the actual deletion once satisfied:  
     - `library-organizer-cli /path/to/your/photos --mode delete-duplicate --input duplicates_results.json`
9. **Scan per-folder media counts and sizes** (read-only, writes a JSON report):
   - `library-organizer-cli /path/to/your/photos --mode scan`
   - With a custom report path: `library-organizer-cli /path/to/your/photos --mode scan --output my_scan.json`
10. **Rename files in a single folder** (non-recursive) to a numbered pattern:
   - `library-organizer-cli /path/to/single/folder --mode rename --name vacation`
   - Files become `vacation (01).ext`, `vacation (02).ext`, … ordered by creation time (then modification time). Omit `--name` to use the default base name `file`.

By default, progress is printed as human-readable text. If you are integrating this tool into a GUI or another system, you can switch to JSON progress events with:

- `library-organizer-cli /path/to/your/photos --progress-format json`

### User-defined skipped folders (optional)

Recursive scans skip built-in directory names (`staging`, `organized`, `logs`, `results`). You can skip additional **folder basenames** (case-insensitive, anywhere under the tree) with an optional JSON file:

- **Default path:** `./results/ignored-folders.json` (relative to the working directory when you run the command).
- **Schema:** `{"folders": ["folder_1", "folder_2", ...]}` — each value is a **directory name**, not a full path.
- **Custom path:** `--ignore-config /path/to/your.json`

This applies to **`--mode all`**, **`flatten`**, **`find-duplicate`**, **`compare`**, and **`scan`**. It does **not** apply to **`organize`** (which only reads `source_root/staging`) or to **`sync`**, **`delete-duplicate`**, or **`rename`**.

## How it works and modes

Library Organizer CLI operates in a few distinct modes, controlled by the `--mode` flag:

- **`all` (default)**:
  - Flattens your library into a staging workspace (handling nested folders and inconsistent structures).
  - Organizes the flattened media into a clean, date-based layout such as `YYYY/MM-MonthName`.
  - With `--output-folder`, flatten uses `output_folder/staging` and the organize stage writes under `output_folder/organized` (same parent-directory convention as running flatten and organize separately).
- **`flatten`**:
  - Only performs the flattening step into a staging folder (default: `source_root/staging`).
  - With `--output-folder`, flattened copies go to `output_folder/staging` (the flag is the parent directory, same layout as the default).
  - The JSON report’s `results` field is the full staging path used.
  - Useful if you want to inspect or pre-process the flattened files before organizing.
  - Writes a JSON report to `--output` (default: `./results/flatten_results.json`) with keys `root`, `results`, `total_scanned`, `total_staged`, and `total_bytes`.
  - **`--mode organize`** reads from `source_root/staging`. Use the same `source_root` as the `--output-folder` you used for flatten (so staging is under that root), or copy/move so your organize `source_root/staging` matches where flatten wrote files.
- **`organize`**:
  - Assumes you already have a prepared `staging` folder under `source_root/staging`.
  - Only runs the organization step, e.g. to try different layouts or re-run organization without re-scanning the original source.
  - With `--output-folder`, the date-based layout is written to `output_folder/organized` (default when omitted: `source_root/organized`).
- **`find-duplicate`**:
  - Scans all media files, computes content hashes, and produces a JSON report of potential duplicates.
  - When `--output` is not specified, it defaults to `./results/duplicates_results.json` in the current working directory.
- **`compare`**:
  - Recursively scans two folders (`source_root` and `--target`), skipping the same `staging` / `organized` / `logs` / `results` folders and unwanted extensions as the other modes.
  - Computes full-content hashes for all files and compares the sets to identify:
    - Hashes present in both (`matching_files`).
    - Files that only exist in the source tree (`missing_in_target`).
    - Files that only exist in the target tree (`missing_in_source`).
  - Writes a JSON report (defaults to `./results/compare_results.json` if `--output` is not provided) that includes counts plus detailed per-file entries with their content hash.
- **`sync`**:
  - Reuses a `compare_results.json` report (produced by `--mode compare`) to copy missing files between the `source_root` and `--target` directories.
  - Requires a `--direction`:
    - `to-target`: copy entries listed as `missing_in_target` from `source_root` into the target tree.
    - `to-source`: copy entries listed as `missing_in_source` from `--target` back into `source_root`.
    - `both`: run both directions sequentially.
  - By default, the report is read from `./results/compare_results.json`, or you can pass `--input` to point at a specific compare report.
  - Results are written to `./results/sync_results.json` by default (or to the file you pass with `--output`), summarizing how many files were copied and how many errors occurred in each direction.
  - For safety, when using `--direction both` without `--dry-run`, you must also pass `--confirm` to acknowledge the bidirectional copy.
- **`delete-duplicate`**:
  - Reads a duplicate report (from `--mode find-duplicate` or from an external tool that produces the same format) and deletes the duplicate files listed in it, keeping one "original" per group.
  - By default, the report is read from `./results/duplicates_results.json`; use `--input` to point at a different file. The tool also accepts a subset format: `{"delete": {"files": ["path/to/file1", ...], "count": N}}`, e.g. from a GUI that lets you choose which duplicates to remove.
  - Deletions are limited to paths under `source_root`; files outside that root are skipped and reported.
  - A summary is written to `./results/delete_results.json` (or to the path given with `--output`). Use `--dry-run` to see how many files would be deleted without removing anything.
- **`scan`**:
  - Walks `source_root` recursively (using the same media extensions and skip rules as compare/duplicate), then aggregates **per-folder** statistics: direct media file counts and recursive byte totals under each directory.
  - Does not move or rename files; it only reads the filesystem and writes a JSON report. When `--output` is not specified, the report defaults to `./results/scan_results.json` in the current working directory.
- **`rename`**:
  - Operates on **one directory only** (`source_root`): it does not recurse into subfolders. Every file directly in that folder is renamed to `<base> (NN).ext`, with `NN` zero-padded to fit the count (e.g. `file (01).jpg`, `file (02).jpg`).
  - Order is by creation time (best-effort across platforms), then modification time. Set the base name with `--name` (default: `file`). Renaming uses a two-phase pass to avoid name collisions while reordering.

For modes that copy, move, delete, or reorganize library files (`all`, `flatten`, `organize`, `find-duplicate`, `compare`, `sync`, `delete-duplicate`), you can add `--dry-run` where supported to preview planned actions. **`scan` is read-only.** **`rename` does not implement `--dry-run`**—try it on a copy of the folder if you want a safe rehearsal. This dry-run guidance is recommended when pointing the tool at a large or valuable library for the first time.

## Mode–arguments mapping

| Mode | Arguments (required and optional with defaults) |
|------|--------------------------------------------------|
| **all** | `source_root` (required)<br>`--dry-run` (optional, default: false)<br>`--mode` (optional, default: all)<br>`--output-folder` (optional; parent directory — flatten to `output_folder/staging`, organize to `output_folder/organized`; defaults when omitted: `source_root/staging` and `source_root/organized`)<br>`--ignore-config` (optional; default: ./results/ignored-folders.json)<br>`--progress-format` (optional, default: text) |
| **flatten** | `source_root` (required)<br>`--dry-run` (optional, default: false)<br>`--mode` (optional, default: all)<br>`--output-folder` (optional; parent directory for flatten staging — writes to `output_folder/staging`; default when omitted: `source_root/staging`)<br>`--output` (optional, default: ./results/flatten_results.json)<br>`--ignore-config` (optional; default: ./results/ignored-folders.json)<br>`--progress-format` (optional, default: text) |
| **organize** | `source_root` (required)<br>`--dry-run` (optional, default: false)<br>`--mode` (optional, default: all)<br>`--output-folder` (optional; parent directory for the organized tree — writes to `output_folder/organized`; default when omitted: `source_root/organized`)<br>`--progress-format` (optional, default: text) |
| **find-duplicate** | `source_root` (required)<br>`--dry-run` (optional, default: false)<br>`--mode` (optional, default: all)<br>`--output` (optional, default: ./results/duplicates_results.json)<br>`--ignore-config` (optional; default: ./results/ignored-folders.json)<br>`--progress-format` (optional, default: text) |
| **compare** | `source_root` (required)<br>`--dry-run` (optional, default: false)<br>`--mode` (optional, default: all)<br>`--output` (optional, default: ./results/compare_results.json)<br>`--target` (required)<br>`--ignore-config` (optional; default: ./results/ignored-folders.json)<br>`--progress-format` (optional, default: text) |
| **sync** | `source_root` (required)<br>`--dry-run` (optional, default: false)<br>`--mode` (optional, default: all)<br>`--output` (optional, default: ./results/sync_results.json)<br>`--target` (required)<br>`--direction` (required: to-target \| to-source \| both)<br>`--input` (optional, default: ./results/compare_results.json)<br>`--confirm` (optional, default: false; required when --direction both without --dry-run)<br>`--progress-format` (optional, default: text) |
| **delete-duplicate** | `source_root` (required)<br>`--dry-run` (optional, default: false)<br>`--mode` (optional, default: all)<br>`--output` (optional, default: ./results/delete_results.json)<br>`--input` (optional, default: ./results/duplicates_results.json)<br>`--progress-format` (optional, default: text)<br><br>`--input` can be either:<br><br>1) A duplicates report (default) produced by **find-duplicate**: `{"groups": [...]}` (deletes every file in each group except the first)<br><br>2) A Delete-list file (e.g. produced by a GUI), containing only the paths you want deleted:<br><br>```json: {"count": 2,"delete": {"files": ["F:/Media/Library/duplicates/file_1.jpg",...]}}```<br><br>Example:<br>`library-organizer-cli /path/to/your/photos --mode delete-duplicate --input ./results/duplicates_results.json --dry-run` |
| **scan** | `source_root` (required)<br>`--dry-run` (optional, no effect; scan is read-only)<br>`--mode` (optional, default: all)<br>`--output` (optional, default: ./results/scan_results.json)<br>`--ignore-config` (optional; default: ./results/ignored-folders.json)<br>`--progress-format` (optional, default: text) |
| **rename** | `source_root` (required; single folder, non-recursive)<br>`--dry-run` (optional, not applied)<br>`--mode` (optional, default: all)<br>`--name` (optional, default: file — base name for `NAME (NN).ext`)<br>`--progress-format` (optional, default: text) |

## Safety and best practices

- **Keep a backup**: Before running Library Organizer CLI on irreplaceable media, ensure you have a verified backup (external drive, NAS, or cloud).
- **Start small**: Test on a small subset (e.g. a single folder) first to confirm the layout and behavior match your expectations.
- **Use `--dry-run` initially**: Always run with `--dry-run` when trying a new mode or pointing to a new library root (where the mode supports it); only drop `--dry-run` once you are satisfied with the planned changes. `scan` is read-only; `rename` does not support `--dry-run`, so use a copy of the folder to test.
- **Avoid network paths for heavy operations**: For large libraries, consider working on a local or fast-attached disk to reduce the risk of network hiccups and improve performance.
- **Review duplicate reports carefully**: Treat the duplicate JSON report as a guide; confirm before deleting any files, especially if they live in different backup locations.

## Final Tips for Success

1. **Duplicate Handling:** If you have two different photos named `IMG_001.jpg`, they will appear in your organized folder as `IMG_001.jpg` and `IMG_001_1.jpg`.
2. **Videos:** This script works for videos too! While many videos don't have "EXIF," the script will catch the oldest file system date to place them in the correct month.
3. **Non-Image Files:** The tool now **only processes image and video files**, using centralized extension lists in `constants.py` (via `is_media_file`). Other file types (documents, system junk, etc.) are ignored automatically.

## Project structure (for developers)

- **Top-level**:
  - `pyproject.toml`: Project metadata, dependencies, and CLI entry point (`library-organizer-cli` -> `library_organizer_cli.main:main`).
  - `scripts/initialize.sh`: Helper script to create `.venv` and install dependencies in editable mode (`pip install -e ".[dev]"`).
  - `scripts/build.sh`: Uses PyInstaller (`library-organizer-cli.spec`) to build a standalone executable.
- **Package** (`src/library_organizer_cli/`):
  - `main.py`: Main entry point; parses CLI args and dispatches to the appropriate pipeline.
  - `cli.py`: Defines CLI interface, modes (`all`, `flatten`, `organize`, `find-duplicate`, `compare`, `sync`, `delete-duplicate`, `scan`, `rename`), `--dry-run`, `--output`, `--output-folder` (parent dir for `…/staging` and/or `…/organized`), `--target`, `--direction`, `--input`, `--confirm`, `--name`, `--ignore-config`, and `--progress-format`.
  - `pipeline.py`: High-level workflows for flattening, organizing into `YYYY/MM-MonthName` folders, running duplicate detection, comparing two folder trees, syncing missing files based on a compare report, deleting duplicates from a report, per-folder media scanning, and single-folder renames, including summaries and cleanup.
  - `extractor.py`: EXIF and filesystem metadata reading and logging, including a unified "true date" calculation per file.
  - `duplicate.py`: Two-pass hashing (partial then full) and grouping logic for detecting duplicate files, plus JSON report generation.
  - `scan.py`: Recursive media discovery aligned with compare/duplicate rules; per-folder direct counts and recursive byte totals for `--mode scan`.
  - `renamer.py`: Non-recursive rename to `base (NN).ext` ordered by creation/modification time.
  - `progress.py`: Progress callback abstraction that supports text progress bars and JSON progress events.
  - `compare.py`: Hash-based folder comparison (source vs target) with concurrency, shared skip rules, and a machine-readable JSON report.
  - `ignore_config.py`: Loads optional `./results/ignored-folders.json` (`{"folders": ["name", ...]}`) to extend directory basename skips during recursive walks.
  - `sync.py`: Logic for reading a compare report and copying missing files between source and target according to the requested direction.
  - `__init__.py`, `__main__.py`: Package bootstrap and version metadata.

```text
library-organizer-cli/
├─ README.md
├─ pyproject.toml
├─ scripts/
│  ├─ initialize.sh
│  └─ build.sh
├─ entry.py
├─ library-organizer-cli.spec
├─ src/
│  └─ library_organizer_cli/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ main.py
│     ├─ cli.py
│     ├─ pipeline.py
│     ├─ extractor.py
│     ├─ duplicate.py
│     ├─ scan.py
│     ├─ renamer.py
│     ├─ progress.py
│     ├─ compare.py
│     ├─ sync.py
│     └─ ignore_config.py
└─ .cursor/, .vscode/, logs/, dist/, build/, and other tooling/generated folders
```

## Contributing and development

- **Set up a dev environment**:
  1. Clone the repository and `cd` into it.
  2. Run `bash scripts/initialize.sh` to create `.venv` and install dependencies (including dev tools like `ruff` and `pyinstaller`).
  3. Activate the virtual environment:
     - Windows (Git Bash / WSL): `source .venv/Scripts/activate`
     - Linux/macOS: `source .venv/bin/activate`
- **Run the tool in editable mode**:
  - With the environment active, run `library-organizer-cli --help` or any of the commands from the **Quick start** section.
- **Code quality**:
  - Lint with `ruff`: `ruff check .`
  - Follow the existing formatting/typing style (e.g. `from __future__ import annotations`, type hints, and 100-character line length).
- **Building**:
  - Build an executable with `bash scripts/build.sh` (from the project root, with the virtual environment active).

## Troubleshooting and FAQs

- **The command is not found**  
  Ensure your virtual environment is activated, or that your Python/scripts directory is on `PATH`. From a fresh clone, run `bash scripts/initialize.sh` then `source .venv/Scripts/activate` (or `.venv/bin/activate` on Linux/macOS).

- **Nothing seems to happen / no files are moved**  
  Check whether you are using `--dry-run`. In dry-run mode the tool only prints planned actions and progress; remove `--dry-run` once you’re comfortable with the preview.

- **The tool says "No files found to process."**  
  Confirm that the `source_root` path is correct and that it contains supported media file types (and not just sidecar/metadata files with skipped extensions like `.ini`, `.db`, `.txt`, `.log`, `.tmp`).

- **Duplicate report exists but I’m not sure how to use it**  
  Open the generated JSON (default `duplicates_results.json`) in a viewer or script. Each group lists a hash and files that share it; by default, the first file in each group is the best candidate for an “original”, and subsequent entries are likely copies. To remove the duplicates, run `library-organizer-cli /path/to/source --mode delete-duplicate --input duplicates_results.json` (use `--dry-run` first to preview).

- **Performance is slow on a huge library**  
  Try running on a faster local disk, close other heavy I/O tasks, and, if needed, run duplicates on a pre-flattened `staging` folder to avoid scanning a complex directory tree repeatedly.

## License and acknowledgements

- **License**: _(Add your chosen license here, e.g. MIT, Apache-2.0, etc.)_
- **Acknowledgements**:
  - [`exifread`](https://github.com/ianare/exif-py) for EXIF metadata parsing.
  - [`xxhash`](https://github.com/Cyan4973/xxHash) for fast, non-cryptographic hashing used during duplicate detection.

## FAQ and knowledge

### Understanding the Log Files

The script creates a `logs/` folder at the root of your source directory. Every time you run it, it generates a new file named by the current timestamp (e.g., `2026-03-15__14-30.log`).

| Log Level | What it means | Action Required |
| --- | --- | --- |
| **WARNING** | A file had corrupted EXIF data or a non-standard date format. | None. The script automatically falls back to the file system date. |
| **ERROR** | A file couldn't be copied (likely "Permission Denied" or "File in Use"). | Close any apps (like Photoshop or Windows Photos) and re-run. |
| **INFO** | (If added) General progress updates. | Just for your information. |

### Progress output for Electron or other GUIs

To drive a progress bar from an external process (e.g. Electron + React), run the CLI with `--progress-format json`. Stdout will then emit one JSON object per line:

- **Progress lines:** `{"type": "progress", "stage": "Staging", "phase": "Scanning", "current": 10, "total": 100, "file": "D:/Photos/a.jpg", "file_size_bytes": 12345, "processed_bytes": 67890, "total_bytes": 12345678}` — `file`, `file_size_bytes`, `processed_bytes`, and `total_bytes` are always present (POSIX path string / bytes values, or `null` when not applicable).
- **Final summary (organize):** `{"type": "summary", "action": "organize", "mode": "all", "scanned": 100, "staged": 100, "organized": 98, "errors": 2, "verified": true, ...}`
- **Final summary (flatten):** `{"type": "summary", "action": "organize", "mode": "flatten", "scanned": 100, "staged": 100, "organized": 0, "errors": 0, "verified": true, "report_path": "..."}`
- **Final summary (duplicate finder):** `{"type": "summary", "action": "duplicate_finder", "scanned": 50, "duplicate_groups": 2, "duplicate_files": 5, "report_path": "..."}`
- **Final summary (scan):** `{"type": "summary", "action": "scan", "total_files": 100, "total_bytes": 12345678, "folder_count": 12, "report_path": "..."}`
- **Final summary (rename):** `{"type": "summary", "action": "rename", "exit_code": 0, "directory": "...", "base_name": "file"}`

Spawn the process (e.g. `library-organizer-cli.exe --progress-format json --mode all "D:\Photos"`), read stdout line by line, `JSON.parse` each line, and update your UI from the `progress` and `summary` objects. Logs remain only in the `logs/` folder; they are never written to stdout.
