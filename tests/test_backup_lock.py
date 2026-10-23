import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import (
    BackupLockError,
    acquire_backup_lock,
)


class TestBackupLock(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_lock_acquired(self):
        with acquire_backup_lock(self.root):
            self.assertTrue(
                (self.root / ".iphone-backup-cli.lock").is_file()
            )

    def test_second_operation_rejected(self):
        with acquire_backup_lock(self.root):
            with self.assertRaisesRegex(
                BackupLockError, "already running"
            ):
                with acquire_backup_lock(self.root):
                    pass

    def test_lock_released_after_operation(self):
        with acquire_backup_lock(self.root):
            pass

        with acquire_backup_lock(self.root):
            pass

    def test_lock_released_after_exception(self):
        with self.assertRaisesRegex(RuntimeError, "Simulated failure"):
            with acquire_backup_lock(self.root):
                raise RuntimeError("Simulated failure")

        with acquire_backup_lock(self.root):
            pass

    def test_symlink_lock_rejected(self):
        lock = self.root / ".iphone-backup-cli.lock"
        lock.symlink_to(self.root / "missing")

        with self.assertRaises(BackupLockError):
            with acquire_backup_lock(self.root):
                pass


    def test_replaced_root_rejected_before_lock_creation(self):
        destination = self.root / "Backups"
        previous = self.root / "PreviousBackups"
        destination.mkdir()
        original_stat = destination.stat()
        signature = (original_stat.st_dev, original_stat.st_ino)
        original_open = os.open
        replaced = False

        def replace_before_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is None and Path(path) == destination:
                destination.rename(previous)
                destination.mkdir()
                replaced = True
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with patch(
            "iphone_backup_cli.backup_lock.os.open",
            side_effect=replace_before_open,
        ):
            with self.assertRaises(BackupLockError):
                with acquire_backup_lock(
                    destination,
                    expected_signature=signature,
                ):
                    self.fail("Replaced destination was accepted.")

        self.assertTrue(replaced)
        self.assertFalse((destination / ".iphone-backup-cli.lock").exists())
        self.assertFalse((previous / ".iphone-backup-cli.lock").exists())

    def test_lock_open_uses_pinned_directory_after_path_replacement(self):
        destination = self.root / "Backups"
        previous = self.root / "PreviousBackups"
        destination.mkdir()
        original_stat = destination.stat()
        signature = (original_stat.st_dev, original_stat.st_ino)
        original_open = os.open
        replaced = False

        def replace_before_lock(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is not None and path == ".iphone-backup-cli.lock":
                destination.rename(previous)
                destination.mkdir()
                replaced = True
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with patch(
            "iphone_backup_cli.backup_lock.os.open",
            side_effect=replace_before_lock,
        ):
            with acquire_backup_lock(
                destination,
                expected_signature=signature,
            ):
                self.assertTrue(replaced)
                self.assertTrue((previous / ".iphone-backup-cli.lock").is_file())
                self.assertFalse((destination / ".iphone-backup-cli.lock").exists())

        self.assertFalse((destination / ".iphone-backup-cli.lock").exists())


if __name__ == "__main__":
    unittest.main()
