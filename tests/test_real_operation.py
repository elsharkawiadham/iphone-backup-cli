import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import (
    BackupLockError,
    acquire_backup_lock,
)
from iphone_backup_cli.real_operation import (
    create_guarded_real_operation,
)


class TestRealOperation(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.mount = Path(temp.name).resolve()
        self.root = self.mount / "Backups"
        self.root.mkdir()
        self.device = "a" * 40

        self.args = (
            str(self.root),
            str(self.mount),
            "mock-volume-uuid",
            self.device,
        )

        targets = (
            "iphone_backup_cli.execution_preflight.verify_storage",
            "iphone_backup_cli.execution_preflight.verify_backup_encryption",
            "iphone_backup_cli.real_backup_plan.verify_storage",
            "iphone_backup_cli.real_operation.verify_storage",
        )

        for target in targets:
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

        patcher = patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            return_value=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch(
            "iphone_backup_cli.real_backup_plan.IDEVICEBACKUP2",
            Path(sys.executable),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unique_operation_and_planning_record(self):
        with create_guarded_real_operation(*self.args) as prepared:
            self.assertTrue(prepared.path.is_dir())
            self.assertEqual(prepared.plan.cwd, prepared.path)
            self.assertEqual(prepared.plan.command[-1], ".")
            self.assertFalse(prepared.plan.target.exists())

            record = json.loads(
                (prepared.path / "planning.json").read_text()
            )

            self.assertEqual(record["state"], "planned_only")
            self.assertFalse(record["transfer_started"])
            self.assertFalse(record["backup_verified"])

    def test_lock_held_during_planning(self):
        with create_guarded_real_operation(*self.args):
            with self.assertRaises(BackupLockError):
                with acquire_backup_lock(self.root):
                    pass

    def test_lock_released_after_planning(self):
        with create_guarded_real_operation(*self.args):
            pass

        with acquire_backup_lock(self.root):
            pass

    def test_second_operation_preserves_first(self):
        with create_guarded_real_operation(*self.args) as first:
            first_path = first.path

        with create_guarded_real_operation(*self.args) as second:
            second_path = second.path

        self.assertNotEqual(first_path, second_path)
        self.assertTrue((first_path / "planning.json").exists())
        self.assertTrue((second_path / "planning.json").exists())

    def test_encryption_failure_creates_no_operation(self):
        with patch(
            "iphone_backup_cli.execution_preflight.verify_backup_encryption",
            side_effect=ValueError("Encryption unavailable"),
        ):
            with self.assertRaises(ValueError):
                with create_guarded_real_operation(*self.args):
                    pass

        self.assertFalse(
            list(self.root.glob(".iphone-backup-operation-*"))
        )


if __name__ == "__main__":
    unittest.main()
