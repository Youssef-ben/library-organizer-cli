from __future__ import annotations

import io
import logging
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
from pathlib import Path

import exifread

LOGGER = logging.getLogger(__name__)

_EXIF_DATE_TAGS = (
    "EXIF DateTimeOriginal",
    "EXIF DateTimeDigitized",
    "Image DateTime",
)

_EXIF_DATE_FORMATS = (
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def configure_warning_log(log_dir: str | Path | None = None) -> Path:
    """
    Configure application logging to write only to a log file (no stdout/stderr).

    All loggers propagate to the root logger, which gets a single FileHandler.
    This keeps diagnostics in files only; stdout is reserved for progress and summaries.

    Args:
        log_dir: Directory for the log file. If None, uses ./logs (cwd).

    Returns:
        The path to the log file (log_dir / "{timestamp}.log").
    """
    if log_dir is None:
        log_dir = Path("./logs")
    else:
        log_dir = Path(log_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d__%H-%M")
    resolved_log_path = log_dir / f"{timestamp}.log"
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(resolved_log_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(file_handler)
    root.setLevel(logging.WARNING)
    return resolved_log_path


def _get_raw_exif(file_path: Path) -> dict:
    """
    Centralized EXIF extraction.
    Opens the file once and captures all internal library warnings.
    """
    try:
        with file_path.open("rb") as image_file:
            capture_stream = io.StringIO()
            with redirect_stdout(capture_stream), redirect_stderr(capture_stream):
                tags = exifread.process_file(image_file, details=False)

            captured_output = capture_stream.getvalue().strip()
            if captured_output:
                for line in captured_output.splitlines():
                    LOGGER.warning("%s: [%s]", line.strip(), file_path)
            return tags
    except Exception as exc:
        if "File format not recognized." not in str(exc):
            LOGGER.error("Error reading EXIF for %s: %s", file_path, exc)
        return {}


def _parse_exif_date(value: object) -> date | None:
    """Parses EXIF string values into a simple date object."""
    text = str(value).strip()
    if not text:
        return None

    for fmt in _EXIF_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def get_true_date(file_path: str | Path) -> date:
    """
    Determine the 'True Date' (no time).
    Logic: min(EXIF tags, File Creation, File Modification)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    candidate_dates: list[date] = []

    tags = _get_raw_exif(path)
    for tag_name in _EXIF_DATE_TAGS:
        parsed = _parse_exif_date(tags.get(tag_name))
        if parsed:
            candidate_dates.append(parsed)

    stats = path.stat()
    candidate_dates.append(datetime.fromtimestamp(stats.st_ctime).date())
    candidate_dates.append(datetime.fromtimestamp(stats.st_mtime).date())

    if not candidate_dates:
        raise ValueError(f"No usable date metadata found for: {file_path}")

    return min(candidate_dates)


def get_formatted_date_string(file_path: str | Path) -> str:
    """
    Return: 'Filename - YYYY-MM-DD'
    """
    path = Path(file_path)
    oldest_date = get_true_date(path)
    return f"{path.name} - {oldest_date.isoformat()}"


def get_image_metadata_report(file_path: str | Path) -> str:
    """
    Returns a human-readable summary of the file metadata.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    stats = path.stat()
    fs_created = datetime.fromtimestamp(stats.st_ctime).date()
    fs_modified = datetime.fromtimestamp(stats.st_mtime).date()

    tags = _get_raw_exif(path)

    lines = [
        f"File: {path.name}",
        f"FS Created: {fs_created}",
        f"FS Modified: {fs_modified}",
        "EXIF Dates Found:",
    ]

    exif_found = False
    for tag_name in _EXIF_DATE_TAGS:
        val = tags.get(tag_name)
        if val:
            lines.append(f"  - {tag_name}: {val}")
            exif_found = True

    if not exif_found:
        lines.append("  - No valid EXIF date tags found.")

    return "\n".join(lines)

