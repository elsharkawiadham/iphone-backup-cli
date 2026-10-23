import tempfile
import unittest
from pathlib import Path

from iphone_backup_cli.backup_command import build_backup_command


class TestBackupCommand(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name).resolve()
        self.device = "00008130-TESTDEVICE123456"

    def test_standard_backup_command(self):
        command = build_backup_command(
            self.device, self.destination
        )
        self.assertEqual(command, [
            "idevicebackup2",
            "-u",
            self.device,
            "-i",
            "backup",
            str(self.destination),
        ])

    def test_full_backup_command(self):
        command = build_backup_command(
            self.device, self.destination, full=True
        )
        self.assertEqual(command[-3:], [
            "backup",
            "--full",
            str(self.destination),
        ])

    def test_missing_destination_rejected(self):
        with self.assertRaises(FileNotFoundError):
            build_backup_command(
                self.device,
                self.destination / "missing",
            )

    def test_invalid_device_rejected(self):
        with self.assertRaisesRegex(
            ValueError, "Invalid device identifier"
        ):
            build_backup_command("", self.destination)


if __name__ == "__main__":
    unittest.main()
