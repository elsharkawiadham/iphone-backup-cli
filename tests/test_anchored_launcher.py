import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "native"
    / "AnchoredLauncher.c"
)

PROFILE = """
(version 1)
(deny default)
(allow process*)
(allow file-read*)
(allow mach-lookup)
(allow sysctl-read)
(allow file-write* (literal "/dev/null"))
(allow file-write* (subpath (param "WRITABLE_ROOT")))
"""

WRITER = (
    "from pathlib import Path;"
    "Path('probe.bin').write_bytes(b'anchored')"
)


@unittest.skipUnless(sys.platform == "darwin", "macOS only")
class TestAnchoredLauncher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)

        cls.launcher = Path(cls.build.name) / "launcher"

        subprocess.run(
            [
                "xcrun",
                "clang",
                str(SOURCE),
                "-Wall",
                "-Wextra",
                "-Werror",
                "-o",
                str(cls.launcher),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.root = Path(temporary.name).resolve()
        self.allowed = self.root / "allowed"
        self.allowed.mkdir()

    def launch(self, fd, command):
        return subprocess.run(
            [str(self.launcher), str(fd), *command],
            pass_fds=(fd,),
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_invalid_descriptor_rejected(self):
        result = subprocess.run(
            [
                str(self.launcher),
                "-1",
                sys.executable,
                "-I",
                "-c",
                "pass",
            ],
            capture_output=True,
            timeout=15,
        )

        self.assertEqual(result.returncode, 65)

    def test_original_directory_survives_replacement(self):
        fd = os.open(
            self.allowed,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )

        try:
            moved = self.root / "moved"
            self.allowed.rename(moved)
            self.allowed.mkdir()

            result = self.launch(
                fd,
                [sys.executable, "-I", "-c", WRITER],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (moved / "probe.bin").read_bytes(),
                b"anchored",
            )
            self.assertFalse((self.allowed / "probe.bin").exists())
        finally:
            os.close(fd)

    def test_sandbox_allows_original_destination(self):
        fd = os.open(
            self.allowed,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )

        try:
            result = self.launch(
                fd,
                [
                    "/usr/bin/sandbox-exec",
                    "-D",
                    f"WRITABLE_ROOT={self.allowed}",
                    "-p",
                    PROFILE,
                    sys.executable,
                    "-I",
                    "-c",
                    WRITER,
                ],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((self.allowed / "probe.bin").is_file())
        finally:
            os.close(fd)

    def test_sandbox_cannot_write_to_replacement(self):
        fd = os.open(
            self.allowed,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )

        try:
            moved = self.root / "moved"
            self.allowed.rename(moved)
            self.allowed.mkdir()

            result = self.launch(
                fd,
                [
                    "/usr/bin/sandbox-exec",
                    "-D",
                    f"WRITABLE_ROOT={self.allowed}",
                    "-p",
                    PROFILE,
                    sys.executable,
                    "-I",
                    "-c",
                    WRITER,
                ],
            )

            self.assertFalse((self.allowed / "probe.bin").exists())

            if result.returncode == 0:
                self.assertEqual(
                    (moved / "probe.bin").read_bytes(),
                    b"anchored",
                )
        finally:
            os.close(fd)


if __name__ == "__main__":
    unittest.main()
