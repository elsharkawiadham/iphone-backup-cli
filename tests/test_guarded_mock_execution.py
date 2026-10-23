import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import BackupLockError, acquire_backup_lock
from iphone_backup_cli.backup_process import run_monitored_command
from iphone_backup_cli.guarded_mock_execution import run_guarded_mock_execution
from iphone_backup_cli.storage import StorageUnavailableError


class TestGuardedMockExecution(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.mount = Path(temporary.name).resolve()
        self.root = self.mount / "Backups"
        self.root.mkdir()

        self.args = (
            str(self.root),
            str(self.mount),
            "mock-volume-uuid",
            "a" * 40,
        )

        targets = (
            "iphone_backup_cli.execution_preflight.verify_storage",
            "iphone_backup_cli.execution_preflight.verify_backup_encryption",
            "iphone_backup_cli.real_backup_plan.verify_storage",
            "iphone_backup_cli.real_operation.verify_storage",
            "iphone_backup_cli.guarded_mock_execution.verify_storage",
        )

        for target in targets:
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

        mount_patcher = patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            return_value=True,
        )
        mount_patcher.start()
        self.addCleanup(mount_patcher.stop)

        executable_patcher = patch(
            "iphone_backup_cli.real_backup_plan.IDEVICEBACKUP2",
            Path(sys.executable),
        )
        executable_patcher.start()
        self.addCleanup(executable_patcher.stop)

    def test_success_is_mock_only(self):
        result = run_guarded_mock_execution(*self.args)
        self.assertEqual(result.status, "mock_succeeded")
        self.assertEqual(result.exit_code, 0)

        record = json.loads(
            (result.operation / "mock-result.json").read_text()
        )

        self.assertFalse(record["transfer_started"])
        self.assertFalse(record["backup_verified"])
        self.assertTrue((result.operation / "planning.json").exists())

    def test_failure_is_preserved(self):
        result = run_guarded_mock_execution(
            *self.args, scenario="failure"
        )
        self.assertEqual(result.status, "mock_failed")
        self.assertEqual(result.exit_code, 6)
        self.assertTrue(
            (result.operation / "mock-result.json").exists()
        )

    def test_timeout_is_preserved(self):
        result = run_guarded_mock_execution(
            *self.args, scenario="timeout"
        )
        self.assertEqual(result.status, "mock_timed_out")
        self.assertEqual(result.exit_code, 7)

    def test_lock_held_during_launch(self):
        def inspect(command, **kwargs):
            self.assertEqual(command[0], "/usr/bin/sandbox-exec")
            self.assertNotIn("idevicebackup2", command)
            kwargs["health_check"]()

            with self.assertRaises(BackupLockError):
                with acquire_backup_lock(self.root):
                    pass

            return run_monitored_command(command, **kwargs)

        with patch(
            "iphone_backup_cli.guarded_mock_execution.run_monitored_command",
            side_effect=inspect,
        ):
            result = run_guarded_mock_execution(*self.args)

        self.assertEqual(result.exit_code, 0)

    def test_storage_failure_before_launch(self):
        with patch(
            "iphone_backup_cli.guarded_mock_execution.verify_storage",
            side_effect=StorageUnavailableError("SSD unavailable"),
        ):
            with self.assertRaises(StorageUnavailableError):
                run_guarded_mock_execution(*self.args)

        operations = list(
            self.root.glob(".iphone-backup-operation-*")
        )
        self.assertEqual(len(operations), 1)
        self.assertTrue((operations[0] / "planning.json").exists())
        self.assertFalse((operations[0] / "mock-result.json").exists())


if __name__ == "__main__":
    unittest.main()
