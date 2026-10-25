"""Negative capability tests for the macOS USB-only sandbox."""

import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iphone_backup_cli.backup_sandbox import (
    BackupSandboxError,
    SANDBOX_PROFILE,
    USBMUX_SANDBOX_PROFILE,
    prepare_sandboxed_command,
)


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox only")
class TestUSBSandbox(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def run_worker(self, code, *args):
        command, cwd = prepare_sandboxed_command(
            [sys.executable, "-I", "-c", code, *map(str, args)],
            self.root,
            allow_usbmux=True,
        )

        return subprocess.run(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_default_profile_does_not_gain_usb_permission(self):
        command, _ = prepare_sandboxed_command(
            [sys.executable, "-I", "-c", "pass"],
            self.root,
        )

        self.assertEqual(command[4], SANDBOX_PROFILE)
        self.assertNotIn("usbmuxd", command[4])
        self.assertIn("usbmuxd", USBMUX_SANDBOX_PROFILE)

    def test_invalid_usb_option_is_rejected(self):
        with self.assertRaises(BackupSandboxError):
            prepare_sandboxed_command(
                [sys.executable, "-I", "-c", "pass"],
                self.root,
                allow_usbmux="true",
            )

    def test_tcp_loopback_connection_denied(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        worker = """
import socket
import sys

try:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(2)
    connection.connect(("127.0.0.1", int(sys.argv[1])))
except PermissionError:
    sys.exit(0)
except OSError:
    sys.exit(4)
else:
    connection.close()
    sys.exit(9)
"""
        result = self.run_worker(worker, port)

        self.assertEqual(
            result.returncode, 0,
            f"TCP restriction not confirmed: {result.stderr[-300:]}",
        )

    def test_unrelated_unix_socket_connection_denied(self):
        socket_path = self.root / "unrelated.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(str(socket_path))
        server.listen(1)

        worker = """
import socket
import sys

try:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(2)
    connection.connect(sys.argv[1])
except PermissionError:
    sys.exit(0)
except OSError:
    sys.exit(4)
else:
    connection.close()
    sys.exit(9)
"""
        result = self.run_worker(worker, socket_path)

        self.assertEqual(
            result.returncode, 0,
            f"Unrelated socket restriction not confirmed: {result.stderr[-300:]}",
        )


if __name__ == "__main__":
    unittest.main()
