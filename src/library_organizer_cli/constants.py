from __future__ import annotations

from pathlib import Path

# Centralized configuration for media files and directory skipping.
# Only files with these extensions are considered by scanning/compare/duplicate logic.

IMAGE_FILE_EXTENSIONS: set[str] = {
    # Common raster / exchange
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jfif",
    ".jpeg",
    ".jpg",
    ".pcx",
    ".png",
    ".psd",
    ".tga",
    ".tif",
    ".tiff",
    ".webp",
    # Camera RAW / DNG (incl. typical 2000s–present bodies)
    ".3fr",
    ".arw",
    ".bay",
    ".cr2",
    ".cr3",
    ".crw",
    ".dcr",
    ".dng",
    ".erf",
    ".iiq",
    ".kdc",
    ".mef",
    ".mrw",
    ".nef",
    ".nrw",
    ".orf",
    ".pef",
    ".raf",
    ".raw",
    ".rwl",
    ".rw2",
    ".sr2",
    ".srf",
    ".srw",
    ".x3f",
}

VIDEO_FILE_EXTENSIONS: set[str] = {
    ".3g2",
    ".3gp",
    ".asf",
    ".avi",
    ".dv",
    ".flv",
    ".m2ts",
    ".m2v",
    ".m4v",
    ".mkv",
    ".mod",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".rm",
    ".rmvb",
    ".tod",
    ".thm",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
}

# Directories that should be skipped during scanning/walking.
SKIP_DIR_NAMES: set[str] = {"staging", "organized", "logs", "results"}

def is_media_file(path: Path) -> bool:
    """
    Return True if the path has an image or video extension.
    """
    suffix = path.suffix.lower()
    return suffix in IMAGE_FILE_EXTENSIONS or suffix in VIDEO_FILE_EXTENSIONS
