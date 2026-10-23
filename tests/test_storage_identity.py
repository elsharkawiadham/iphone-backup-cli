import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.storage import StorageUnavailableError
from iphone_backup_cli.storage_identity import (
    capture_destination_identity,
    check_destination_identity,
)


class TestStorageIdentity(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.mount = Path(temporary.name).resolve() / "volume"
        self.destination = self.mount / "Backups"
        self.destination.mkdir(parents=True)

        patcher = patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            return_value=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def capture(self):
        return capture_destination_identity(
            str(self.destination),
            str(self.mount),
        )

    def test_unchanged_destination_accepted(self):
        identity = self.capture()
        self.assertTrue(check_destination_identity(identity))

    def test_replaced_destination_rejected(self):
        identity = self.capture()

        self.destination.rename(self.mount / "OldBackups")
        self.destination.mkdir()

        with self.assertRaises(StorageUnavailableError):
            check_destination_identity(identity)

    def test_missing_destination_rejected(self):
        identity = self.capture()
        self.destination.rmdir()

        with self.assertRaises(StorageUnavailableError):
            check_destination_identity(identity)

    def test_mount_disappearance_rejected(self):
        identity = self.capture()

        with patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            return_value=False,
        ):
            with self.assertRaises(StorageUnavailableError):
                check_destination_identity(identity)

    def test_symlink_destination_rejected(self):
        self.destination.rmdir()
        self.destination.symlink_to(self.mount)

        with self.assertRaises(StorageUnavailableError):
            self.capture()

    def test_ancestor_symlink_within_mount_rejected(self):
        parent = self.mount / "parent"
        parent.symlink_to(self.mount, target_is_directory=True)
        with self.assertRaisesRegex(StorageUnavailableError, "canonical"):
            capture_destination_identity(parent / "Backups", self.mount)

    def test_ancestor_redirect_after_capture_rejected(self):
        parent = self.mount / "parent"
        parent.mkdir()
        destination = parent / "Backups"
        destination.mkdir()
        identity = capture_destination_identity(destination, self.mount)

        parent.rename(self.mount / "original")
        parent.symlink_to(self.mount, target_is_directory=True)
        with self.assertRaises(StorageUnavailableError):
            check_destination_identity(identity)

    def test_mount_symlink_rejected(self):
        alias = self.mount.parent / "alias"
        alias.symlink_to(self.mount, target_is_directory=True)
        with self.assertRaises(StorageUnavailableError):
            capture_destination_identity(alias / "Backups", alias)

    def test_replaced_mount_rejected(self):
        identity = self.capture()
        self.mount.rename(self.mount.parent / "original")
        self.destination.mkdir(parents=True)
        with self.assertRaises(StorageUnavailableError):
            check_destination_identity(identity)

    def test_fallback_directory_is_not_a_mount(self):
        with patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            return_value=False,
        ):
            with self.assertRaises(StorageUnavailableError):
                self.capture()

    def test_filesystem_error_fails_closed(self):
        with patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            side_effect=OSError("Filesystem disconnected"),
        ):
            with self.assertRaises(StorageUnavailableError):
                self.capture()


if __name__ == "__main__":
    unittest.main()
