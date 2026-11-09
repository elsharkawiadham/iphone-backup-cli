"""Mock-only tests. No real process, device query, or backup command runs."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from iphone_backup_cli.backup_lock import BackupLockError
from iphone_backup_cli.backup_process import BackupProcessError
from iphone_backup_cli.backup_sandbox import USBMUX_SANDBOX_PROFILE
from iphone_backup_cli.real_backup_plan import IDEVICEBACKUP2
from iphone_backup_cli.simulated_execution_boundary import (
    run_checked_harmless_simulation,
)
from iphone_backup_cli.storage import StorageUnavailableError

MODULE = "iphone_backup_cli.simulated_execution_boundary"


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox-exec required")
class TestSimulatedExecutionBoundary(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.root = Path(temporary.name).resolve() / "Backups"
        self.root.mkdir()
        self.operation = self.root / (
            ".iphone-backup-operation-" + "0" * 32
        )
        self.operation.mkdir()
        self.device = "a" * 40
        self.mount = str(self.root.parent)
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

        started = {
            "gate": patch(
                "iphone_backup_cli.prelaunch_orchestration."
                "require_fresh_prelaunch_safety",
                return_value=True,
            ),
            "storage": patch(f"{MODULE}.verify_storage"),
            "identity": patch(f"{MODULE}.check_destination_identity"),
            "target": patch(
                f"{MODULE}.check_new_backup_target",
                return_value=self.plan.target,
            ),
            "runner": patch(
                f"{MODULE}.run_monitored_command", return_value=0
            ),
            "popen": patch(
                "subprocess.Popen",
                side_effect=AssertionError("No real process may start."),
            ),
        }
        for name, patcher in started.items():
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def run_it(self):
        return run_checked_harmless_simulation(
            self.prepared, str(self.root), self.mount, self.uuid, self.device
        )

    def assert_blocked(self, error_type):
        with self.assertRaises(error_type):
            self.run_it()
        self.runner.assert_not_called()

    def test_success_claims_no_transfer_or_verification(self):
        result = self.run_it()
        self.assertEqual(result.status, "simulation_succeeded")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.transfer_started)
        self.assertFalse(result.backup_verified)
        self.runner.assert_called_once()

    def test_only_fixed_noop_reaches_supervisor(self):
        self.run_it()
        command = self.runner.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/sandbox-exec")
        self.assertEqual(command[-4:], [sys.executable, "-I", "-c", "pass"])
        self.assertFalse(any("idevicebackup2" in a for a in command))
        self.assertNotIn("usbmuxd", command[4])
        self.assertEqual(self.runner.call_args.kwargs["cwd"], self.operation)
        self.assertNotIn("pass_fds", self.runner.call_args.kwargs)

    def test_safety_gate_refusal_blocks_supervisor(self):
        self.gate.side_effect = RuntimeError("Safety check failed")
        self.assert_blocked(RuntimeError)

    def test_invalid_planned_command_blocks_everything(self):
        self.plan.command = self.command[:-1] + ("--full", ".")
        self.assert_blocked(ValueError)
        self.gate.assert_not_called()

    def test_storage_failure_before_launch(self):
        self.storage.side_effect = StorageUnavailableError("SSD unavailable")
        self.assert_blocked(StorageUnavailableError)

    def test_storage_failure_during_monitoring(self):
        def fake(command, **kwargs):
            self.storage.side_effect = StorageUnavailableError("SSD lost")
            kwargs["health_check"]()
            return 0

        self.runner.side_effect = fake
        with self.assertRaises(StorageUnavailableError):
            self.run_it()

    def test_lost_lock_blocks_launch(self):
        self.lock.check.side_effect = BackupLockError("Lock lost")
        self.assert_blocked(BackupLockError)

    def test_changed_target_rejected(self):
        self.target.return_value = self.operation / ("b" * 40)
        self.assert_blocked(ValueError)

    def test_changed_identity_rejected(self):
        self.identity.side_effect = StorageUnavailableError("Changed")
        self.assert_blocked(StorageUnavailableError)

    def test_supervisor_failure_propagates_without_quarantine(self):
        self.runner.side_effect = BackupProcessError(
            "failed", reason="exit", returncode=7
        )
        with self.assertRaises(BackupProcessError) as raised:
            self.run_it()
        self.assertEqual(raised.exception.returncode, 7)
        self.lock.quarantine.assert_not_called()

    def test_timeout_propagates(self):
        self.runner.side_effect = BackupProcessError(
            "timed out", reason="timeout"
        )
        with self.assertRaises(BackupProcessError) as raised:
            self.run_it()
        self.assertEqual(raised.exception.reason, "timeout")

    def test_uncertain_cleanup_quarantines_and_reraises(self):
        self.runner.side_effect = BackupProcessError(
            "cleanup unconfirmed", reason="timeout", cleanup_failed=True
        )
        with self.assertRaises(BackupProcessError):
            self.run_it()
        self.lock.quarantine.assert_called_once_with(self.operation.name)

    def test_unexpected_exit_codes_rejected(self):
        for value in (1, True, None, 0.0, "0"):
            with self.subTest(value=value):
                self.runner.return_value = value
                with self.assertRaises(ValueError):
                    self.run_it()

    def test_sandbox_working_directory_mismatch_rejected(self):
        with patch(
            f"{MODULE}.prepare_sandboxed_command",
            return_value=(["x"], Path("/elsewhere")),
        ):
            self.assert_blocked(ValueError)


if __name__ == "__main__":
    unittest.main()
