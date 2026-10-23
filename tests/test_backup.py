import unittest
from unittest.mock import patch

from iphone_backup_cli.backup import run_backup_dry_run
from iphone_backup_cli.encryption import EncryptionCheckError
from iphone_backup_cli.storage import StorageUnavailableError


class TestBackupDryRun(unittest.TestCase):

    def setUp(self):
        self.device_a = "a" * 40
        self.device_b = "b" * 40

        self.settings = {
            "backup_destination": "/Volumes/TestSSD/Backups",
            "backup_volume": {
                "mount_point": "/Volumes/TestSSD",
                "volume_uuid": "test-uuid",
            },
        }

        self.config_mock = patch(
            "iphone_backup_cli.backup.load_config",
            return_value=self.settings,
        )
        self.storage_mock = patch(
            "iphone_backup_cli.backup.verify_storage",
            return_value=True,
        )
        self.devices_mock = patch(
            "iphone_backup_cli.backup.list_connected_devices",
            return_value=[self.device_a],
        )

        self.encryption_mock = patch(
            "iphone_backup_cli.backup.verify_backup_encryption",
            return_value=True,
        )
        self.verify_encryption = self.encryption_mock.start()
        self.addCleanup(self.encryption_mock.stop)

        self.target_mock = patch(
            "iphone_backup_cli.backup.check_new_backup_target",
            return_value="/Volumes/TestSSD/Backups/new-device",
        )
        self.check_target = self.target_mock.start()
        self.addCleanup(self.target_mock.stop)

        self.command_mock = patch(
            "iphone_backup_cli.backup.build_backup_command",
            return_value=["idevicebackup2", "backup", "test-directory"],
        )

        self.build_command = self.command_mock.start()
        self.addCleanup(self.command_mock.stop)

        self.load_config = self.config_mock.start()
        self.verify_storage = self.storage_mock.start()
        self.list_devices = self.devices_mock.start()

        self.addCleanup(self.config_mock.stop)
        self.addCleanup(self.storage_mock.stop)
        self.addCleanup(self.devices_mock.stop)

    def test_single_device_success(self):
        result = run_backup_dry_run()

        self.assertEqual(result, 0)
        self.verify_storage.assert_called_once_with(
            "/Volumes/TestSSD/Backups",
            "/Volumes/TestSSD",
            "test-uuid",
        )
        self.list_devices.assert_called_once()

    def test_missing_configuration(self):
        self.load_config.return_value = None

        result = run_backup_dry_run()

        self.assertEqual(result, 1)
        self.verify_storage.assert_not_called()
        self.list_devices.assert_not_called()

    def test_disconnected_storage(self):
        self.verify_storage.side_effect = StorageUnavailableError(
            "External SSD disconnected"
        )

        result = run_backup_dry_run()

        self.assertEqual(result, 1)
        self.list_devices.assert_not_called()

    def test_no_connected_devices(self):
        self.list_devices.return_value = []

        result = run_backup_dry_run()

        self.assertEqual(result, 1)

    def test_multiple_devices_requires_selection(self):
        self.list_devices.return_value = [
            self.device_a,
            self.device_b,
        ]

        result = run_backup_dry_run()

        self.assertEqual(result, 1)

    def test_explicit_device_selection(self):
        self.list_devices.return_value = [
            self.device_a,
            self.device_b,
        ]

        result = run_backup_dry_run(
            device_id=self.device_b
        )

        self.assertEqual(result, 0)

    def test_unknown_device_rejected(self):
        result = run_backup_dry_run(
            device_id=self.device_b
        )

        self.assertEqual(result, 1)


    def test_backup_command_prepared(self):
        result = run_backup_dry_run()

        self.assertEqual(result, 0)
        self.build_command.assert_called_once_with(
            self.device_a,
            "/Volumes/TestSSD/Backups",
        )

    def test_invalid_backup_command_rejected(self):
        self.build_command.side_effect = ValueError(
            "Invalid backup destination"
        )

        result = run_backup_dry_run()

        self.assertEqual(result, 1)


    def test_encryption_checked_for_selected_device(self):
        result = run_backup_dry_run()

        self.assertEqual(result, 0)
        self.verify_encryption.assert_called_once_with(self.device_a)

    def test_disabled_encryption_blocks_backup(self):
        self.verify_encryption.side_effect = EncryptionCheckError(
            "Backup encryption is disabled"
        )

        result = run_backup_dry_run()

        self.assertEqual(result, 1)
        self.build_command.assert_not_called()


    def test_new_backup_target_checked(self):
        result = run_backup_dry_run()

        self.assertEqual(result, 0)
        self.check_target.assert_called_once_with(
            "/Volumes/TestSSD/Backups",
            self.device_a,
        )

    def test_existing_backup_target_blocks_operation(self):
        from iphone_backup_cli.backup_target import BackupTargetError

        self.check_target.side_effect = BackupTargetError(
            "A backup target already exists for this device."
        )

        result = run_backup_dry_run()

        self.assertEqual(result, 1)
        self.build_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
