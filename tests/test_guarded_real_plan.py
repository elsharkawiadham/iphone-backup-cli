import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import (
    BackupLockError,
    acquire_backup_lock,
)
from iphone_backup_cli.backup_target import BackupTargetError
from iphone_backup_cli.guarded_real_plan import (
    guarded_real_backup_plan,
)


class TestGuardedRealPlan(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.mount = Path(temporary.name).resolve()
        self.root = self.mount / "Backups"
        self.root.mkdir()

        self.operation = self.root / (
            ".iphone-backup-operation-" + uuid.uuid4().hex
        )
        self.operation.mkdir()

        self.device = "a" * 40

        self.args = (
            str(self.root),
            str(self.operation),
            str(self.mount),
            "test-volume-uuid",
            self.device,
        )

        targets = (
            "iphone_backup_cli.execution_preflight.verify_storage",
            "iphone_backup_cli.execution_preflight.verify_backup_encryption",
            "iphone_backup_cli.real_backup_plan.verify_storage",
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

    def test_valid_plan_under_lock(self):
        with guarded_real_backup_plan(*self.args) as plan:
            self.assertEqual(plan.cwd, self.operation)
            self.assertEqual(plan.command[-1], ".")
            self.assertFalse(plan.target.exists())

    def test_second_lock_blocked_while_planning(self):
        with guarded_real_backup_plan(*self.args):
            with self.assertRaises(BackupLockError):
                with acquire_backup_lock(self.root):
                    pass

    def test_lock_released_after_planning(self):
        with guarded_real_backup_plan(*self.args):
            pass

        with acquire_backup_lock(self.root):
            pass

    def test_existing_device_backup_rejected(self):
        (self.root / self.device).mkdir()

        with self.assertRaises(BackupTargetError):
            with guarded_real_backup_plan(*self.args):
                pass

    def test_nonempty_operation_rejected(self):
        (self.operation / "existing.txt").write_text("preserve")

        with self.assertRaisesRegex(ValueError, "must be empty"):
            with guarded_real_backup_plan(*self.args):
                pass

        self.assertEqual(
            (self.operation / "existing.txt").read_text(),
            "preserve",
        )

        with acquire_backup_lock(self.root):
            pass


if __name__ == "__main__":
    unittest.main()
