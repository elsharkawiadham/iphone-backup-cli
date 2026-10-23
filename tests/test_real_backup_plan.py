import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.real_backup_plan import (
    prepare_real_backup_plan,
)
from iphone_backup_cli.backup_target import BackupTargetError
from iphone_backup_cli.storage import StorageUnavailableError


class TestRealBackupPlan(unittest.TestCase):

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

        self.mount = Path(self.temporary.name).resolve()
        self.root = self.mount / "Backups"
        self.root.mkdir()

        self.operation = (
            self.root / f".iphone-backup-operation-{uuid.uuid4().hex}"
        )
        self.operation.mkdir()

        self.device = "a" * 40

        mount_patch = patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            return_value=True,
        )
        mount_patch.start()
        self.addCleanup(mount_patch.stop)

        storage_patch = patch(
            "iphone_backup_cli.real_backup_plan.verify_storage"
        )
        self.verify_storage = storage_patch.start()
        self.addCleanup(storage_patch.stop)

        executable_patch = patch(
            "iphone_backup_cli.real_backup_plan.IDEVICEBACKUP2",
            Path(sys.executable),
        )
        executable_patch.start()
        self.addCleanup(executable_patch.stop)

    def prepare(self, operation=None, device=None):
        return prepare_real_backup_plan(
            str(self.root),
            str(operation or self.operation),
            str(self.mount),
            "mock-volume-uuid",
            device or self.device,
        )

    def test_command_uses_relative_destination(self):
        plan = self.prepare()

        self.assertEqual(plan.command[-1], ".")
        self.assertEqual(plan.cwd, self.operation)
        self.assertEqual(plan.target, self.operation / self.device)
        self.assertIn("sandbox-exec", plan.command[0])
        self.assertEqual(
            plan.command[-6:-1],
            (
                sys.executable,
                "-u",
                self.device,
                "-i",
                "backup",
            ),
        )

    def test_existing_device_target_rejected(self):
        (self.operation / self.device).mkdir()

        with self.assertRaises(BackupTargetError):
            self.prepare()

    def test_unapproved_operation_name_rejected(self):
        with self.assertRaises(ValueError):
            self.prepare(operation=self.root)

    def test_operation_outside_root_rejected(self):
        other = self.mount / (
            ".iphone-backup-operation-" + uuid.uuid4().hex
        )
        other.mkdir()

        with self.assertRaises(ValueError):
            self.prepare(operation=other)

    def test_storage_failure_blocks_planning(self):
        self.verify_storage.side_effect = StorageUnavailableError(
            "Volume unavailable"
        )

        with self.assertRaises(StorageUnavailableError):
            self.prepare()

    def test_symlink_operation_rejected(self):
        link = self.root / (
            ".iphone-backup-operation-" + uuid.uuid4().hex
        )
        link.symlink_to(self.operation, target_is_directory=True)

        with self.assertRaises(ValueError):
            self.prepare(operation=link)


if __name__ == "__main__":
    unittest.main()
