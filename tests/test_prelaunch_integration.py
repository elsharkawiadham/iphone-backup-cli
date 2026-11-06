"""Integration tests with a fake callback. No subprocess launches."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from iphone_backup_cli.backup_encryption import BackupEncryptionError
from iphone_backup_cli.backup_sandbox import USBMUX_SANDBOX_PROFILE
from iphone_backup_cli.prelaunch_orchestration import (
    prepare_checked_launch_intent,
)
from iphone_backup_cli.real_backup_plan import IDEVICEBACKUP2
from iphone_backup_cli.storage import StorageUnavailableError


class TestPrelaunchIntegration(unittest.TestCase):

    def setUp(self):
        self.root = Path("/mock-volume/Backups")
        self.operation = self.root / (
            ".iphone-backup-operation-" + "0" * 32
        )
        self.device = "a" * 40
        self.mount = "/mock-volume"
        self.uuid = "mock-uuid"

        self.command = (
            "/usr/bin/sandbox-exec",
            "-D",
            f"WRITABLE_ROOT={self.operation}",
            "-p",
            USBMUX_SANDBOX_PROFILE,
            str(IDEVICEBACKUP2),
            "-u",
            self.device,
            "backup",
            ".",
        )

        self.plan = SimpleNamespace(
            command=self.command,
            cwd=self.operation,
            target=self.operation / self.device,
            root_identity=object(),
            operation_identity=object(),
        )

        self.lock = Mock()
        self.prepared = SimpleNamespace(
            path=self.operation,
            plan=self.plan,
            lock=self.lock,
            state="planned_only",
        )

        self.fake_launcher = Mock(return_value="simulation_only")

        patches = {
            "storage": patch(
                "iphone_backup_cli.prelaunch_safety.verify_storage"
            ),
            "identity": patch(
                "iphone_backup_cli.prelaunch_safety.check_destination_identity"
            ),
            "target": patch(
                "iphone_backup_cli.prelaunch_safety.check_new_backup_target",
                return_value=self.plan.target,
            ),
            "encryption": patch(
                "iphone_backup_cli.prelaunch_safety.require_backup_encryption",
                return_value=True,
            ),
            "process": patch(
                "subprocess.Popen",
                side_effect=AssertionError(
                    "A real process must never start."
                ),
            ),
        }

        for name, patcher in patches.items():
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def simulate(self):
        intent = prepare_checked_launch_intent(
            self.prepared,
            str(self.root),
            self.mount,
            self.uuid,
            self.device,
        )

        # Test-only callback. Never executes the planned command.
        return self.fake_launcher(intent.command, intent.cwd)

    def assert_blocked(self, error_type):
        with self.assertRaises(error_type):
            self.simulate()
        self.fake_launcher.assert_not_called()
        self.process.assert_not_called()

    def test_success_reaches_fake_launcher(self):
        self.assertEqual(self.simulate(), "simulation_only")
        self.fake_launcher.assert_called_once_with(
            self.command, self.operation
        )
        self.encryption.assert_called_once()
        self.process.assert_not_called()

    def test_encryption_failure_blocks_launcher(self):
        self.encryption.side_effect = BackupEncryptionError(
            "Encryption unavailable"
        )
        self.assert_blocked(BackupEncryptionError)

    def test_false_encryption_blocks_launcher(self):
        self.encryption.return_value = False
        self.assert_blocked(BackupEncryptionError)

    def test_storage_failure_blocks_launcher(self):
        self.storage.side_effect = StorageUnavailableError(
            "SSD unavailable"
        )
        self.assert_blocked(StorageUnavailableError)

    def test_storage_lost_after_query_blocks_launcher(self):
        self.storage.side_effect = [
            None,
            None,
            StorageUnavailableError("SSD disconnected"),
        ]
        self.assert_blocked(StorageUnavailableError)

    def test_identity_failure_blocks_launcher(self):
        self.identity.side_effect = StorageUnavailableError(
            "Destination changed"
        )
        self.assert_blocked(StorageUnavailableError)

    def test_lock_failure_blocks_launcher(self):
        self.lock.check.side_effect = RuntimeError(
            "Lock lost"
        )
        self.assert_blocked(RuntimeError)

    def test_target_change_blocks_launcher(self):
        self.target.return_value = self.operation / ("b" * 40)
        self.assert_blocked(ValueError)

    def test_modified_command_blocks_launcher(self):
        modified = list(self.command)
        modified[8] = "restore"
        self.plan.command = tuple(modified)
        self.assert_blocked(ValueError)
        self.encryption.assert_not_called()

    def test_command_mutated_during_query_blocks_launcher(self):
        def mutate(*args):
            self.plan.command = ("unexpected",)
            return True

        self.encryption.side_effect = mutate
        self.assert_blocked(ValueError)

    def test_invalid_operation_state_blocks_launcher(self):
        self.prepared.state = "running"
        self.assert_blocked(ValueError)
        self.encryption.assert_not_called()


if __name__ == "__main__":
    unittest.main()
