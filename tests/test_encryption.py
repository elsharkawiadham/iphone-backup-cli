import subprocess
import unittest
from unittest.mock import patch

from iphone_backup_cli.encryption import (
    EncryptionCheckError,
    verify_backup_encryption,
)


class TestEncryption(unittest.TestCase):
    def setUp(self):
        self.device = "00008130-TESTDEVICE123456"

    @patch("iphone_backup_cli.encryption.subprocess.run")
    def test_encryption_enabled(self, mock_run):
        mock_run.return_value.stdout = "true\n"

        self.assertTrue(verify_backup_encryption(self.device))
        self.assertEqual(
            mock_run.call_args.args[0][1:3],
            ["-u", self.device],
        )

    @patch("iphone_backup_cli.encryption.subprocess.run")
    def test_encryption_disabled(self, mock_run):
        mock_run.return_value.stdout = "false\n"

        with self.assertRaises(EncryptionCheckError):
            verify_backup_encryption(self.device)

    @patch("iphone_backup_cli.encryption.subprocess.run")
    def test_unknown_encryption_state(self, mock_run):
        mock_run.return_value.stdout = ""

        with self.assertRaises(EncryptionCheckError):
            verify_backup_encryption(self.device)

    @patch("iphone_backup_cli.encryption.subprocess.run")
    def test_command_failure(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            "ideviceinfo", 15
        )

        with self.assertRaises(EncryptionCheckError):
            verify_backup_encryption(self.device)

    def test_invalid_device(self):
        with self.assertRaises(EncryptionCheckError):
            verify_backup_encryption("")


if __name__ == "__main__":
    unittest.main()
