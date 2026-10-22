import plistlib
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from iphone_backup_cli.storage import (
    StorageUnavailableError,
    verify_storage,
)


class TestStorage(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.root = Path(temp.name).resolve()
        self.mount = self.root / "volume"
        self.destination = self.mount / "backups"
        self.destination.mkdir(parents=True)

    def mock_diskutil(self, uuid="test-uuid"):
        return CompletedProcess(
            args=["diskutil"],
            returncode=0,
            stdout=plistlib.dumps({
                "VolumeUUID": uuid,
                "MountPoint": str(self.mount),
            }),
            stderr=b"",
        )

    def check(self, destination=None):
        return verify_storage(
            destination=destination or self.destination,
            mount_point=self.mount,
            expected_uuid="test-uuid",
        )

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_valid_storage(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil()

        self.assertTrue(self.check())

    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_disconnected_storage(self, mock_mount):
        mock_mount.return_value = False

        with self.assertRaises(StorageUnavailableError):
            self.check()

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_wrong_uuid(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil("wrong-uuid")

        with self.assertRaises(StorageUnavailableError):
            self.check()

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_outside_volume(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil()

        outside = self.root / "outside"
        outside.mkdir()

        with self.assertRaises(StorageUnavailableError):
            self.check(outside)

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_missing_destination(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil()

        with self.assertRaises(StorageUnavailableError):
            self.check(self.mount / "missing")


if __name__ == "__main__":
    unittest.main()
