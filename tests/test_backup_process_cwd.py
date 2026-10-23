import sys
import tempfile
import unittest
from pathlib import Path

from iphone_backup_cli.backup_process import run_monitored_command


class TestBackupProcessCwd(unittest.TestCase):

    def test_process_uses_requested_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()

            result = run_monitored_command(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "from pathlib import Path; Path('cwd-test.bin').write_bytes(b'ok')",
                ],
                cwd=root,
            )

            self.assertEqual(result, 0)
            self.assertEqual((root / "cwd-test.bin").read_bytes(), b"ok")

    def test_symlink_directory_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real = root / "real"
            link = root / "link"
            real.mkdir()
            link.symlink_to(real, target_is_directory=True)

            with self.assertRaises(ValueError):
                run_monitored_command(
                    [sys.executable, "-c", "pass"],
                    cwd=link,
                )


if __name__ == "__main__":
    unittest.main()
