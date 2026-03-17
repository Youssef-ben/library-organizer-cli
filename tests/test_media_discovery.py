from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from library_organizer_cli.media_discovery import collect_media_paths


class TestMediaDiscovery(unittest.TestCase):
    def test_skips_skip_dir_names_and_collects_media_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "ok").mkdir()
            (root / "results").mkdir()
            (root / "staging").mkdir()
            (root / "ok" / "a.jpg").write_bytes(b"x")
            (root / "results" / "b.jpg").write_bytes(b"x")
            (root / "staging" / "c.jpg").write_bytes(b"x")
            (root / "ok" / "readme.txt").write_text("x", encoding="utf-8")

            paths = collect_media_paths(
                root,
                mode="scan",
                progress_callback=lambda *args: None,
            )
            rel = {p.relative_to(root).as_posix() for p in paths}
            self.assertEqual(rel, {"ok/a.jpg"})

    def test_extra_skip_dir_names_prunes_custom_output_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            (root / "ok").mkdir()
            (root / "CustomTarget").mkdir()

            (root / "ok" / "a.jpg").write_bytes(b"x")
            (root / "CustomTarget" / "b.jpg").write_bytes(b"x")

            paths = collect_media_paths(
                root,
                mode="scan",
                progress_callback=lambda *args: None,
                extra_skip_dir_names={"customtarget"},
            )
            rel = {p.relative_to(root).as_posix() for p in paths}
            self.assertEqual(rel, {"ok/a.jpg"})


if __name__ == "__main__":
    unittest.main()
