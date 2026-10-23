import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iphone_backup_cli.backup_sandbox import (
    BackupSandboxError,
    prepare_sandboxed_command,
)


class TestBackupSandbox(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name).resolve()
        self.allowed = self.root / "allowed"
        self.blocked = self.root / "blocked"

        self.allowed.mkdir()
        self.blocked.mkdir()

    def launch(self, code):
        return prepare_sandboxed_command(
            [sys.executable, "-I", "-c", code],
            self.allowed,
        )

    def test_invalid_executable_rejected(self):
        with self.assertRaises(BackupSandboxError):
            prepare_sandboxed_command(
                ["python", "-c", "pass"],
                self.allowed,
            )

    def test_symlink_directory_rejected(self):
        link = self.root / "link"
        link.symlink_to(self.allowed, target_is_directory=True)

        with self.assertRaises(BackupSandboxError):
            prepare_sandboxed_command(
                [sys.executable, "-c", "pass"],
                link,
            )

    def test_writes_outside_directory_blocked(self):
        code = """
from pathlib import Path
Path("inside.bin").write_bytes(b"inside")
try:
    Path("../blocked/outside.bin").write_bytes(b"outside")
except OSError:
    pass
"""
        command, cwd = self.launch(code)

        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.allowed / "inside.bin").read_bytes(),
            b"inside",
        )
        self.assertFalse(
            (self.blocked / "outside.bin").exists()
        )

    def test_replacement_directory_not_written(self):
        code = """
from pathlib import Path
import sys

Path("before.bin").write_bytes(b"before")
print("READY", flush=True)
sys.stdin.readline()

try:
    Path("after.bin").write_bytes(b"after")
    print("WRITTEN", flush=True)
except OSError:
    print("BLOCKED", flush=True)
"""
        command, cwd = self.launch(code)
        moved = self.root / "moved"

        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            import select

            readable, _, _ = select.select(
                [process.stdout], [], [], 10
            )

            self.assertTrue(readable, "Worker did not become ready")
            self.assertEqual(process.stdout.readline().strip(), "READY")

            self.allowed.rename(moved)
            self.allowed.mkdir()

            output, errors = process.communicate(
                input="continue\n",
                timeout=15,
            )

            self.assertEqual(process.returncode, 0, errors)
            self.assertFalse((self.allowed / "after.bin").exists())

            if "WRITTEN" in output:
                self.assertEqual(
                    (moved / "after.bin").read_bytes(),
                    b"after",
                )
            else:
                self.assertIn("BLOCKED", output)

        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    unittest.main()
