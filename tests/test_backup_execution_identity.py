import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from iphone_backup_cli.backup_execution import simulate_backup_execution
from iphone_backup_cli.backup_lock import acquire_backup_lock
from iphone_backup_cli.storage import StorageUnavailableError


class TestBackupExecutionIdentity(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.root = Path(temporary.name).resolve()
        root_stat = self.root.stat()
        identity_patcher = patch(
            "iphone_backup_cli.execution_preflight.capture_destination_identity"
        )
        self.preflight_capture = identity_patcher.start()
        self.preflight_capture.return_value.destination_signature = (
            root_stat.st_dev, root_stat.st_ino
        )
        self.addCleanup(identity_patcher.stop)

        identity_check_patcher = patch(
            "iphone_backup_cli.execution_preflight.check_destination_identity"
        )
        self.preflight_check = identity_check_patcher.start()
        self.addCleanup(identity_check_patcher.stop)

        self.args = (
            str(self.root),
            "/Volumes/TestSSD",
            "test-uuid",
            "a" * 40,
        )

        for function in (
            "verify_storage",
            "verify_backup_encryption",
        ):
            patcher = patch(
                f"iphone_backup_cli.execution_preflight.{function}"
            )
            patcher.start()
            self.addCleanup(patcher.stop)

        storage_patcher = patch(
            "iphone_backup_cli.backup_execution.verify_storage"
        )
        storage_patcher.start()
        self.addCleanup(storage_patcher.stop)

        check_patcher = patch(
            "iphone_backup_cli.backup_execution.check_destination_identity"
        )
        self.check_identity = check_patcher.start()
        self.addCleanup(check_patcher.stop)

    def test_identity_checked_during_simulation(self):
        def inspect(command, timeout, health_check, check_interval):
            health_check()
            health_check()
            return 0

        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command",
            side_effect=inspect,
        ):
            self.assertEqual(simulate_backup_execution(*self.args), 0)

        self.check_identity.assert_has_calls([
            call(self.preflight_capture.return_value),
            call(self.preflight_capture.return_value),
        ])
        self.assertEqual(self.check_identity.call_count, 3)

    def test_identity_change_blocks_simulation(self):
        self.check_identity.side_effect = StorageUnavailableError(
            "Backup destination identity changed."
        )

        def simulate_change(command, timeout, health_check, check_interval):
            health_check()
            return 0

        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command",
            side_effect=simulate_change,
        ):
            with self.assertRaises(StorageUnavailableError):
                simulate_backup_execution(*self.args)

        with acquire_backup_lock(self.root):
            pass


if __name__ == "__main__":
    unittest.main()
