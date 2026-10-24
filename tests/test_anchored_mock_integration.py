import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import BackupLockError, QUARANTINE_NAME
from iphone_backup_cli.backup_process import (
    BackupProcessError,
    BackupProcessInterruptedError,
    run_monitored_command,
)
from iphone_backup_cli.guarded_mock_execution import (
    run_guarded_mock_execution,
)


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "native"
    / "AnchoredLauncher.c"
)


@unittest.skipUnless(sys.platform == "darwin", "macOS only")
class TestAnchoredMockIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)

        cls.launcher = Path(temporary.name) / "launcher"

        subprocess.run(
            [
                "xcrun", "clang", str(SOURCE),
                "-Wall", "-Wextra", "-Werror",
                "-o", str(cls.launcher),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.mount = Path(temporary.name).resolve()
        self.root = self.mount / "Backups"
        self.root.mkdir()

        self.args = (
            str(self.root),
            str(self.mount),
            "test-volume",
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

        binary_patcher = patch(
            "iphone_backup_cli.real_backup_plan.IDEVICEBACKUP2",
            Path(sys.executable),
        )
        binary_patcher.start()
        self.addCleanup(binary_patcher.stop)

    def run_case(self, scenario):
        return run_guarded_mock_execution(
            *self.args,
            scenario=scenario,
            native_launcher=self.launcher,
        )

    def test_anchored_success_and_journal(self):
        result = self.run_case("success")

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.status, "mock_succeeded")

        record = json.loads(
            (result.operation / "mock-result.json").read_text()
        )

        self.assertFalse(record["transfer_started"])
        self.assertFalse(record["backup_verified"])

    def test_anchored_process_failure(self):
        result = self.run_case("failure")

        self.assertEqual(result.exit_code, 6)
        self.assertEqual(result.status, "mock_failed")

    def test_anchored_process_timeout(self):
        result = self.run_case("timeout")

        self.assertEqual(result.exit_code, 7)
        self.assertEqual(result.status, "mock_timed_out")

    def test_descriptor_inherited_by_native_launcher(self):
        original = run_monitored_command

        def inspect(command, **kwargs):
            self.assertEqual(command[0], str(self.launcher))
            self.assertEqual(command[2], "/usr/bin/sandbox-exec")
            self.assertNotIn("cwd", kwargs)

            (fd,) = kwargs["pass_fds"]
            self.assertTrue(stat.S_ISDIR(os.fstat(fd).st_mode))

            return original(command, **kwargs)

        with patch(
            "iphone_backup_cli.guarded_mock_execution.run_monitored_command",
            side_effect=inspect,
        ):
            result = self.run_case("success")

        self.assertEqual(result.exit_code, 0)

    def test_missing_launcher_rejected_before_transfer(self):
        with self.assertRaises(ValueError):
            run_guarded_mock_execution(
                *self.args,
                native_launcher=self.mount / "missing-launcher",
            )

        operations = list(
            self.root.glob(".iphone-backup-operation-*")
        )

        self.assertEqual(len(operations), 1)
        self.assertTrue((operations[0] / "planning.json").exists())
        self.assertFalse((operations[0] / "mock-result.json").exists())


    def test_keyboard_interrupt_never_reports_success(self):
        with patch(
            "iphone_backup_cli.guarded_mock_execution.run_monitored_command",
            side_effect=KeyboardInterrupt(),
        ):
            result = self.run_case("success")

        self.assertEqual(result.status, "mock_interrupted")
        self.assertEqual(result.exit_code, 130)

        record = json.loads(
            (result.operation / "mock-result.json").read_text()
        )

        self.assertEqual(record["status"], "mock_interrupted")
        self.assertFalse(record["backup_verified"])
        self.assertFalse(record["transfer_started"])

    def test_sigterm_has_distinct_terminal_code(self):
        error = BackupProcessInterruptedError(signal.SIGTERM)

        with patch(
            "iphone_backup_cli.guarded_mock_execution.run_monitored_command",
            side_effect=error,
        ):
            result = self.run_case("success")

        self.assertEqual(result.status, "mock_interrupted")
        self.assertEqual(result.exit_code, 143)

    def test_cleanup_uncertainty_quarantines_root(self):
        error = BackupProcessError(
            "Process cleanup could not be confirmed.",
            reason="timeout",
            cleanup_failed=True,
        )

        with patch(
            "iphone_backup_cli.guarded_mock_execution.run_monitored_command",
            side_effect=error,
        ):
            result = self.run_case("timeout")

        self.assertEqual(result.status, "mock_cleanup_unconfirmed")
        self.assertEqual(result.exit_code, 9)

        marker = self.root / QUARANTINE_NAME
        self.assertTrue(marker.is_file())
        self.assertIn(result.operation.name, marker.read_text())

        record = json.loads(
            (result.operation / "mock-result.json").read_text()
        )

        self.assertEqual(record["status"], "mock_cleanup_unconfirmed")
        self.assertFalse(record["backup_verified"])

        with self.assertRaises(BackupLockError):
            self.run_case("success")

        operations = list(
            self.root.glob(".iphone-backup-operation-*")
        )
        self.assertEqual(len(operations), 1)

    def test_failed_quarantine_never_claims_success(self):
        error = BackupProcessError(
            "Process group may still be active.",
            cleanup_failed=True,
        )

        with patch(
            "iphone_backup_cli.guarded_mock_execution.run_monitored_command",
            side_effect=error,
        ), patch(
            "iphone_backup_cli.backup_lock.BackupLockGuard.quarantine",
            side_effect=BackupLockError("Quarantine write failed."),
        ):
            with self.assertRaises(BackupLockError):
                self.run_case("success")

        operations = list(
            self.root.glob(".iphone-backup-operation-*")
        )

        self.assertEqual(len(operations), 1)
        self.assertTrue((operations[0] / "planning.json").exists())
        self.assertFalse((operations[0] / "mock-result.json").exists())

    def test_journal_write_failure_never_claims_success(self):
        original_open = os.open

        def fail_result_journal(path, *args, **kwargs):
            if path == "mock-result.json":
                raise OSError("Simulated result journal I/O failure.")
            return original_open(path, *args, **kwargs)

        with patch(
            "iphone_backup_cli.guarded_mock_execution.os.open",
            side_effect=fail_result_journal,
        ):
            with self.assertRaises(OSError):
                self.run_case("success")

        operations = list(
            self.root.glob(".iphone-backup-operation-*")
        )

        self.assertEqual(len(operations), 1)
        self.assertTrue((operations[0] / "planning.json").exists())
        self.assertFalse((operations[0] / "mock-result.json").exists())


    def run_with_real_signal(self, signum, *, uncertain_cleanup=False):
        """Signal this test process only after supervision is active."""

        original_popen = subprocess.Popen
        spawned = []

        def launch(*args, **kwargs):
            handler = signal.getsignal(signum)

            if not callable(handler):
                raise RuntimeError(
                    "Refusing to signal without a supervised handler."
                )

            child = original_popen(*args, **kwargs)
            spawned.append(child)

            # The supervised handler records this actual OS signal.
            # It does not send the signal to the shell or other apps.
            signal.raise_signal(signum)
            return child

        with patch(
            "iphone_backup_cli.backup_process.subprocess.Popen",
            side_effect=launch,
        ):
            if uncertain_cleanup:
                with patch(
                    "iphone_backup_cli.backup_process._stop_process",
                    return_value=False,
                ):
                    result = self.run_case("timeout")
            else:
                result = self.run_case("timeout")

        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(
            spawned[0].poll(),
            "The native worker was not reaped.",
        )

        return result

    def test_real_sigterm_stops_native_worker(self):
        result = self.run_with_real_signal(signal.SIGTERM)

        self.assertEqual(result.status, "mock_interrupted")
        self.assertEqual(result.exit_code, 143)

        journal = json.loads(
            (result.operation / "mock-result.json").read_text()
        )

        self.assertEqual(journal["status"], "mock_interrupted")
        self.assertFalse(journal["backup_verified"])
        self.assertFalse(journal["transfer_started"])

        self.assertFalse(
            (self.root / QUARANTINE_NAME).exists()
        )

        # Confirm the operation lock was released after cleanup.
        subsequent = self.run_case("success")
        self.assertEqual(subsequent.exit_code, 0)

    def test_real_sigint_stops_native_worker(self):
        result = self.run_with_real_signal(signal.SIGINT)

        self.assertEqual(result.status, "mock_interrupted")
        self.assertEqual(result.exit_code, 130)

        journal = json.loads(
            (result.operation / "mock-result.json").read_text()
        )

        self.assertEqual(journal["status"], "mock_interrupted")
        self.assertFalse(journal["backup_verified"])
        self.assertFalse(journal["transfer_started"])

    def test_actual_worker_with_uncertain_cleanup_is_quarantined(self):
        result = self.run_with_real_signal(
            signal.SIGTERM,
            uncertain_cleanup=True,
        )

        self.assertEqual(
            result.status,
            "mock_cleanup_unconfirmed",
        )
        self.assertEqual(result.exit_code, 9)

        marker = self.root / QUARANTINE_NAME
        self.assertTrue(marker.is_file())

        journal = json.loads(
            (result.operation / "mock-result.json").read_text()
        )

        self.assertEqual(
            journal["status"],
            "mock_cleanup_unconfirmed",
        )
        self.assertFalse(journal["backup_verified"])

        with self.assertRaises(BackupLockError):
            self.run_case("success")


if __name__ == "__main__":
    unittest.main()
