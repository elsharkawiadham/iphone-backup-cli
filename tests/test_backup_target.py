import tempfile
import unittest
from pathlib import Path

from iphone_backup_cli.backup_target import (
    BackupTargetError,
    check_new_backup_target,
)


class TestBackupTarget(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.device = "a" * 40

    def test_new_target_accepted(self):
        target = check_new_backup_target(
            self.root, self.device
        )
        self.assertEqual(target, self.root / self.device)
        self.assertFalse(target.exists())

    def test_existing_backup_rejected(self):
        (self.root / self.device).mkdir()
        with self.assertRaises(BackupTargetError):
            check_new_backup_target(self.root, self.device)

    def test_symlink_target_rejected(self):
        (self.root / self.device).symlink_to(
            self.root / "missing"
        )
        with self.assertRaises(BackupTargetError):
            check_new_backup_target(self.root, self.device)

    def test_invalid_identifier_rejected(self):
        with self.assertRaises(BackupTargetError):
            check_new_backup_target(self.root, "../unsafe")

    def test_missing_root_rejected(self):
        with self.assertRaises(BackupTargetError):
            check_new_backup_target(
                self.root / "missing", self.device
            )


if __name__ == "__main__":
    unittest.main()
