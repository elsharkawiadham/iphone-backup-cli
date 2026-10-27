import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_encryption import (
    BackupEncryptionError,
    require_backup_encryption,
)


class TestBackupEncryption(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.device = "a" * 40

        executable = patch(
            "iphone_backup_cli.backup_encryption.IDEVICEINFO",
            Path(sys.executable),
        )
        executable.start()
        self.addCleanup(executable.stop)

    def query(self, stdout, returncode=0):
        with patch(
            "iphone_backup_cli.backup_encryption.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], returncode, stdout, ""
            ),
        ) as launched:
            outcome = require_backup_encryption(
                self.device, self.directory
            )
        return outcome, launched

    def test_enabled_encryption_accepted(self):
        outcome, launched = self.query("true\n")
        self.assertTrue(outcome)

        command = launched.call_args.args[0]
        self.assertIn("WillEncrypt", command)
        self.assertIn(self.device, command)
        self.assertNotIn("--simple", command)
        self.assertEqual(
            launched.call_args.kwargs["stdin"],
            subprocess.DEVNULL,
        )
        self.assertNotIn(
            "BACKUP_PASSWORD",
            launched.call_args.kwargs["env"],
        )

    def test_numeric_true_accepted(self):
        self.assertTrue(self.query("1\n")[0])

    def test_disabled_encryption_rejected(self):
        for value in ("false", "0"):
            with self.subTest(value=value):
                with self.assertRaises(BackupEncryptionError):
                    self.query(value)

    def test_missing_or_unexpected_response_rejected(self):
        for value in ("", "unknown", "true\nfalse"):
            with self.subTest(value=value):
                with self.assertRaises(BackupEncryptionError):
                    self.query(value)

    def test_query_failure_rejected(self):
        with self.assertRaises(BackupEncryptionError):
            self.query("", returncode=1)

    def test_timeout_rejected(self):
        with patch(
            "iphone_backup_cli.backup_encryption.subprocess.run",
            side_effect=subprocess.TimeoutExpired("query", 15),
        ):
            with self.assertRaises(BackupEncryptionError):
                require_backup_encryption(
                    self.device, self.directory
                )

    def test_invalid_device_rejected(self):
        for device in ("", "-n", "a\0b"):
            with self.subTest(device=device):
                with self.assertRaises(BackupEncryptionError):
                    require_backup_encryption(
                        device, self.directory
                    )

    def test_parent_password_not_inherited(self):
        with patch.dict(
            os.environ,
            {"BACKUP_PASSWORD": "synthetic-test-secret"},
        ):
            _, launched = self.query("true")

        self.assertNotIn(
            "BACKUP_PASSWORD",
            launched.call_args.kwargs["env"],
        )


if __name__ == "__main__":
    unittest.main()
