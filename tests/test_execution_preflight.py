import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import (
    BackupLockError,
    acquire_backup_lock,
)
from iphone_backup_cli.backup_target import BackupTargetError
from iphone_backup_cli.execution_preflight import (
    prepare_backup_execution,
)
from iphone_backup_cli.storage import StorageUnavailableError


class TestExecutionPreflight(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name).resolve()
        self.device = "a" * 40

        self.args = (
            str(self.root),
            "/Volumes/TestSSD",
            "test-uuid",
            self.device,
        )

        storage_patcher = patch(
            "iphone_backup_cli.execution_preflight.verify_storage",
            return_value=True,
        )
        encryption_patcher = patch(
            "iphone_backup_cli.execution_preflight.verify_backup_encryption",
            return_value=True,
        )

        self.verify_storage = storage_patcher.start()
        self.verify_encryption = encryption_patcher.start()

        self.addCleanup(storage_patcher.stop)
        self.addCleanup(encryption_patcher.stop)

    def test_valid_preflight(self):
        with prepare_backup_execution(*self.args) as target:
            self.assertEqual(target, self.root / self.device)
            self.assertFalse(target.exists())
            self.assertTrue(
                (self.root / ".iphone-backup-cli.lock").exists()
            )

        self.assertEqual(self.verify_storage.call_count, 2)
        self.verify_encryption.assert_called_once_with(self.device)

    def test_disconnected_storage_rejected_before_lock(self):
        self.verify_storage.side_effect = StorageUnavailableError(
            "SSD disconnected"
        )

        with self.assertRaises(StorageUnavailableError):
            with prepare_backup_execution(*self.args):
                pass

        self.assertFalse(
            (self.root / ".iphone-backup-cli.lock").exists()
        )
        self.verify_encryption.assert_not_called()

    def test_existing_backup_rejected(self):
        (self.root / self.device).mkdir()

        with self.assertRaises(BackupTargetError):
            with prepare_backup_execution(*self.args):
                pass

    def test_concurrent_operation_rejected(self):
        with acquire_backup_lock(self.root):
            with self.assertRaises(BackupLockError):
                with prepare_backup_execution(*self.args):
                    pass

    def test_second_storage_check_failure(self):
        self.verify_storage.side_effect = [
            True,
            StorageUnavailableError("Volume changed"),
        ]

        with self.assertRaises(StorageUnavailableError):
            with prepare_backup_execution(*self.args):
                pass

        self.assertEqual(self.verify_storage.call_count, 2)
        self.verify_encryption.assert_not_called()


if __name__ == "__main__":
    unittest.main()
