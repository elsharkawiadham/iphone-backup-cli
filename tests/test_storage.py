import plistlib
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from iphone_backup_cli.storage import (
    StorageUnavailableError,
    verify_storage,
    identify_volume,
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
                **({"VolumeUUID": uuid} if uuid is not None else {}),
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


    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_identify_valid_volume(self, mock_mount, mock_run):
        mock_mount.side_effect = lambda p: Path(p) == self.mount
        mock_run.return_value = self.mock_diskutil()

        result = identify_volume(self.destination)

        self.assertEqual(result["mount_point"], str(self.mount))
        self.assertEqual(result["volume_uuid"], "test-uuid")

    def test_identify_missing_directory(self):
        with self.assertRaises(StorageUnavailableError):
            identify_volume(self.root / "missing")

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_identify_missing_uuid(self, mock_mount, mock_run):
        mock_mount.side_effect = lambda p: Path(p) == self.mount
        mock_run.return_value = self.mock_diskutil(uuid=None)

        with self.assertRaises(StorageUnavailableError):
            identify_volume(self.destination)

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_identify_wrong_mount_point(self, mock_mount, mock_run):
        mock_mount.side_effect = lambda p: Path(p) == self.mount

        mock_run.return_value = CompletedProcess(
            args=["diskutil"],
            returncode=0,
            stdout=plistlib.dumps({
                "VolumeUUID": "test-uuid",
                "MountPoint": str(self.root),
            }),
            stderr=b"",
        )

        with self.assertRaises(StorageUnavailableError):
            identify_volume(self.destination)


if __name__ == "__main__":
    unittest.main()


class TestExternalVolumeRequirement(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.mount = self.root / "volume"
        self.destination = self.mount / "backups"
        self.destination.mkdir(parents=True)

    def identify_with_internal_value(self, internal):
        info = {
            "VolumeUUID": "test-uuid",
            "MountPoint": str(self.mount),
        }

        if internal is not None:
            info["Internal"] = internal

        result = CompletedProcess(
            args=["diskutil"],
            returncode=0,
            stdout=plistlib.dumps(info),
            stderr=b"",
        )

        with patch(
            "iphone_backup_cli.storage.os.path.ismount",
            side_effect=lambda path: Path(path) == self.mount,
        ), patch(
            "iphone_backup_cli.storage.subprocess.run",
            return_value=result,
        ):
            return identify_volume(
                self.destination,
                require_external=True,
            )

    def test_external_volume_accepted(self):
        result = self.identify_with_internal_value(False)
        self.assertEqual(result["volume_uuid"], "test-uuid")

    def test_internal_volume_rejected(self):
        with self.assertRaisesRegex(
            StorageUnavailableError, "confirmed external"
        ):
            self.identify_with_internal_value(True)

    def test_unknown_volume_type_rejected(self):
        with self.assertRaisesRegex(
            StorageUnavailableError, "confirmed external"
        ):
            self.identify_with_internal_value(None)
