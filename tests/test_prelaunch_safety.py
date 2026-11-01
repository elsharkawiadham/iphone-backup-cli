import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from iphone_backup_cli.backup_encryption import BackupEncryptionError
from iphone_backup_cli.prelaunch_safety import require_fresh_prelaunch_safety
from iphone_backup_cli.storage import StorageUnavailableError


class TestPrelaunchSafety(unittest.TestCase):

    def setUp(self):
        self.root = Path("/mock-external-volume/Backups")
        self.operation = self.root / ".iphone-backup-operation-test"
        self.device = "a" * 40
        self.mount = "/mock-external-volume"
        self.uuid = "mock-volume-uuid"

        self.lock = Mock()

        self.prepared = SimpleNamespace(
            path=self.operation,
            lock=self.lock,
            plan=SimpleNamespace(
                root_identity=object(),
                operation_identity=object(),
                target=self.operation / self.device,
                cwd=self.operation,
            ),
        )

        patches = {
            "storage": patch(
                "iphone_backup_cli.prelaunch_safety.verify_storage"
            ),
            "identity": patch(
                "iphone_backup_cli.prelaunch_safety.check_destination_identity"
            ),
            "target": patch(
                "iphone_backup_cli.prelaunch_safety.check_new_backup_target",
                return_value=self.prepared.plan.target,
            ),
            "encryption": patch(
                "iphone_backup_cli.prelaunch_safety.require_backup_encryption",
                return_value=True,
            ),
        }

        for name, patcher in patches.items():
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def verify(self):
        return require_fresh_prelaunch_safety(
            self.prepared,
            str(self.root),
            self.mount,
            self.uuid,
            self.device,
        )

    def test_valid_prelaunch_rechecks_everything(self):
        self.assertTrue(self.verify())

        self.assertEqual(self.storage.call_count, 4)
        self.assertEqual(self.identity.call_count, 4)
        self.assertEqual(self.lock.check.call_count, 2)
        self.assertEqual(self.target.call_count, 2)

        self.encryption.assert_called_once_with(
            self.device, self.operation
        )

    def test_false_encryption_result_rejected(self):
        self.encryption.return_value = False

        with self.assertRaises(BackupEncryptionError):
            self.verify()

    def test_disabled_or_unknown_encryption_rejected(self):
        for message in ("Encryption disabled", "Encryption unknown"):
            with self.subTest(message=message):
                self.encryption.side_effect = BackupEncryptionError(message)

                with self.assertRaises(BackupEncryptionError):
                    self.verify()

                self.assertEqual(self.encryption.call_count, 1)
                self.encryption.reset_mock()

    def test_storage_failure_before_query_blocks_encryption_check(self):
        self.storage.side_effect = StorageUnavailableError(
            "SSD disconnected"
        )

        with self.assertRaises(StorageUnavailableError):
            self.verify()

        self.encryption.assert_not_called()

    def test_storage_failure_after_query_is_rejected(self):
        self.storage.side_effect = [
            None,
            None,
            StorageUnavailableError("SSD disconnected after query"),
        ]

        with self.assertRaises(StorageUnavailableError):
            self.verify()

        self.encryption.assert_called_once()

    def test_changed_backup_target_rejected(self):
        self.target.return_value = self.operation / ("b" * 40)

        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.verify()

        self.encryption.assert_not_called()

    def test_changed_working_directory_rejected(self):
        self.prepared.plan.cwd = self.root

        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.verify()

        self.encryption.assert_not_called()

    def test_lost_lock_rejected(self):
        self.lock.check.side_effect = RuntimeError("Backup lock lost")

        with self.assertRaisesRegex(RuntimeError, "Backup lock lost"):
            self.verify()

        self.encryption.assert_not_called()

    def test_identity_change_rejected(self):
        self.identity.side_effect = StorageUnavailableError(
            "Destination identity changed"
        )

        with self.assertRaises(StorageUnavailableError):
            self.verify()

        self.encryption.assert_not_called()


if __name__ == "__main__":
    unittest.main()
