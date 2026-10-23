import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_execution import (
    simulate_backup_execution,
)
from iphone_backup_cli.backup_lock import acquire_backup_lock
from iphone_backup_cli.backup_process import BackupProcessError
from iphone_backup_cli.backup_target import BackupTargetError


class TestBackupExecution(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.root = Path(temp.name).resolve()
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

    def test_successful_simulation(self):
        with patch(
            "iphone_backup_cli.backup_execution.verify_storage"
        ):
            result = simulate_backup_execution(*self.args)
        self.assertEqual(result, 0)
        self.assertFalse((self.root / self.device).exists())

    def test_lock_held_during_process(self):
        def inspect_process(command, timeout, health_check, check_interval):
            self.assertEqual(
                command,
                [sys.executable, "-c", "pass"],
            )
            self.assertEqual(timeout, 10)
            self.assertEqual(check_interval, 1.0)
            self.assertTrue(callable(health_check))

            with self.assertRaises(Exception):
                with acquire_backup_lock(self.root):
                    pass

            return 0

        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command",
            side_effect=inspect_process,
        ) as runner:
            simulate_backup_execution(*self.args)

        runner.assert_called_once()

    def test_existing_target_blocks_process(self):
        (self.root / self.device).mkdir()

        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command"
        ) as runner:
            with self.assertRaises(BackupTargetError):
                simulate_backup_execution(*self.args)

            runner.assert_not_called()

    def test_failed_process_releases_lock(self):
        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command",
            side_effect=BackupProcessError("Simulated failure"),
        ):
            with self.assertRaises(BackupProcessError):
                simulate_backup_execution(*self.args)

        with acquire_backup_lock(self.root):
            pass

    def test_real_backup_command_never_executed(self):
        with patch(
            "iphone_backup_cli.backup_execution.run_monitored_command",
            return_value=0,
        ) as runner:
            simulate_backup_execution(*self.args)

        command = runner.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertNotIn("idevicebackup2", command)


if __name__ == "__main__":
    unittest.main()
