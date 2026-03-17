from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from library_organizer_cli.pipeline import _cleanup_temporary, _rmtree_skip_errors


class TestCleanupTemporary(unittest.TestCase):
    def test_emits_cleanup_progress_before_and_after_rmtree(self) -> None:
        calls: list[tuple] = []

        def cb(*args: object) -> None:
            calls.append(tuple(args))

        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp).resolve() / "staging"
            staging.mkdir()
            (staging / "f.txt").write_text("x", encoding="utf-8")
            path_str = staging.as_posix()

            ok, msg = _cleanup_temporary(staging, True, False, progress_callback=cb)
            self.assertTrue(ok)
            self.assertIn("deleted", msg.lower())
            self.assertFalse(staging.exists())
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][:5], (0, 1, "Cleanup", "Deleting staging", path_str))
            self.assertEqual(calls[1][:5], (1, 1, "Cleanup", "Staging deleted", path_str))

    def test_rmtree_skip_errors_clears_read_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp).resolve() / "staging"
            staging.mkdir()
            f = staging / "readonly.txt"
            f.write_text("x", encoding="utf-8")
            if sys.platform == "win32":
                os.chmod(f, stat.S_IREAD)
            else:
                os.chmod(f, 0o444)

            failed = _rmtree_skip_errors(staging)
            self.assertEqual(failed, [])
            self.assertFalse(staging.exists())


if __name__ == "__main__":
    unittest.main()
