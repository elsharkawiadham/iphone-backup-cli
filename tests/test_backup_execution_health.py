import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_execution import (
    simulate_backup_execution,
)
from iphone_backup_cli.backup_lock import acquire_backup_lock
from iphone_backup_cli.storage import StorageUnavailableError


class TestBackupExecutionHealth(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.root = Path(temporary.name).resolve()
        self.device = "a" * 40
        self.args = (
            str(self.root),
            "/Volumes/TestSSD",
            "test-uuid",
            self.device,
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
        self.monitor_storage = storage_patcher.start()
        self.addCleanup(storage_patcher.stop)

    def test_storage_monitored_while_lock_is_held(self):
        def inspect(command, timeout, health_check, check_interval):
            self.assertEqual(check_interval, 1.0)
            self.assertTrue(callable(health_check))

            health_check()
            health_check()

            self.assertEqual(self.monitor_storage.call_count, 2)

            with self.assertRaises(Exception):
                with acquire_backup_lock(self.root):
                    pass

            return 0

        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command",
            side_effect=inspect,
        ):
            result = simulate_backup_execution(*self.args)

        self.assertEqual(result, 0)

    def test_storage_failure_releases_lock(self):
        self.monitor_storage.side_effect = StorageUnavailableError(
            "SSD disconnected"
        )

        def simulate_failure(
            command, timeout, health_check, check_interval
        ):
            health_check()
            return 0

        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command",
            side_effect=simulate_failure,
        ):
            with self.assertRaises(StorageUnavailableError):
                simulate_backup_execution(*self.args)

        with acquire_backup_lock(self.root):
            pass


if __name__ == "__main__":
    unittest.main()
