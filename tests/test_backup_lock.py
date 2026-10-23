import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
