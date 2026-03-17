from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from library_organizer_cli.ignore_config import (
    IGNORED_FOLDERS_JSON_NAME,
    default_ignored_folders_path,
    load_user_ignored_folder_names,
)


class TestIgnoreConfig(unittest.TestCase):
    def test_default_ignored_folders_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            p = default_ignored_folders_path(cwd)
            self.assertEqual(p, cwd / "results" / IGNORED_FOLDERS_JSON_NAME)

    def test_load_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(
                json.dumps({"folders": ["MyArchive", "exports"]}),
                encoding="utf-8",
            )
            names = load_user_ignored_folder_names(path)
            self.assertEqual(names, {"myarchive", "exports"})

    def test_load_missing_file_returns_empty(self) -> None:
        path = Path(tempfile.gettempdir()) / "nonexistent-ignored-folders-xyz.json"
        self.assertEqual(load_user_ignored_folder_names(path), set())

    def test_load_invalid_json_logs_and_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertLogs("library_organizer_cli.ignore_config", level="WARNING"):
                self.assertEqual(load_user_ignored_folder_names(path), set())

    def test_load_not_object_logs_and_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('["a"]', encoding="utf-8")
            with self.assertLogs("library_organizer_cli.ignore_config", level="WARNING"):
                self.assertEqual(load_user_ignored_folder_names(path), set())

    def test_load_folders_not_list_logs_and_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"folders": "x"}', encoding="utf-8")
            with self.assertLogs("library_organizer_cli.ignore_config", level="WARNING"):
                self.assertEqual(load_user_ignored_folder_names(path), set())

    def test_load_skips_non_string_entries_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(
                json.dumps({"folders": ["keep", 1, None, "Other"]}),
                encoding="utf-8",
            )
            with self.assertLogs("library_organizer_cli.ignore_config", level="WARNING"):
                names = load_user_ignored_folder_names(path)
            self.assertEqual(names, {"keep", "other"})


if __name__ == "__main__":
    unittest.main()
