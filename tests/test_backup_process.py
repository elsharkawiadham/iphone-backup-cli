import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from iphone_backup_cli.backup_process import (
    BackupProcessError,
    BackupProcessInterruptedError,
    _stop_process,
    run_monitored_command,
)
from iphone_backup_cli.storage import StorageUnavailableError


class TestBackupProcess(unittest.TestCase):

    def test_successful_process(self):
        self.assertEqual(run_monitored_command([sys.executable, "-c", "pass"]), 0)

    def test_nonzero_exit_rejected_with_metadata(self):
        with self.assertRaisesRegex(BackupProcessError, "code 7") as raised:
            run_monitored_command([
                sys.executable, "-c", "import sys; sys.exit(7)",
            ])
        self.assertEqual(raised.exception.reason, "exit")
        self.assertEqual(raised.exception.returncode, 7)
        self.assertFalse(raised.exception.cleanup_failed)

    def test_timeout_stops_process(self):
        with self.assertRaisesRegex(BackupProcessError, "timed out") as raised:
            run_monitored_command([
                sys.executable, "-c", "import time; time.sleep(5)",
            ], timeout=0.05)
        self.assertEqual(raised.exception.reason, "timeout")
        self.assertFalse(raised.exception.cleanup_failed)

    def test_invalid_command_rejected(self):
        for command in ([], "command", [""], ["bad\0command"], [1]):
            with self.subTest(command=command), self.assertRaises(ValueError):
                run_monitored_command(command)

    def test_invalid_limits_and_descriptors_rejected_before_launch(self):
        invalid = [
            {"timeout": False}, {"timeout": float("nan")},
            {"timeout": -1}, {"check_interval": 0},
            {"stop_timeout": float("inf")}, {"kill_timeout": -1},
            {"pass_fds": [True]}, {"pass_fds": [-1]},
            {"pass_fds": "1"},
        ]
        with patch("iphone_backup_cli.backup_process.subprocess.Popen") as start:
            for kwargs in invalid:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    run_monitored_command(["simulation"], **kwargs)
        start.assert_not_called()

    def test_interruption_stops_process(self):
        process = MagicMock()
        process.wait.side_effect = [KeyboardInterrupt(), 0]
        process.poll.side_effect = [None, None, 0, 0]
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process):
            with self.assertRaises(KeyboardInterrupt):
                run_monitored_command(["simulation"])
        process.terminate.assert_called_once()

    def test_missing_executable_rejected_with_metadata(self):
        with self.assertRaises(BackupProcessError) as raised:
            run_monitored_command([
                "/nonexistent/iphone-backup-cli-test-program"
            ])
        self.assertEqual(raised.exception.reason, "start")
        self.assertIsNone(raised.exception.returncode)

    @unittest.skipUnless(os.name == "posix", "POSIX process groups")
    def test_launch_creates_session_and_passes_only_requested_descriptors(self):
        process = MagicMock()
        process.wait.return_value = 0
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process) as start:
            run_monitored_command(["simulation"], pass_fds=(3, 5))
        start.assert_called_once_with(
            ["simulation"], stdin=subprocess.DEVNULL,
            start_new_session=True, pass_fds=(3, 5),
        )

    def test_handlers_restored_after_launch_failure(self):
        before = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        with self.assertRaises(BackupProcessError):
            run_monitored_command(["/nonexistent/iphone-backup-cli-test-program"])
        self.assertEqual(before, {s: signal.getsignal(s) for s in before})

    def test_signal_in_launch_handoff_still_stops_returned_process(self):
        process = MagicMock()
        process.poll.side_effect = [None, None, 0, 0]
        process.wait.return_value = 0

        def launch(*_args, **_kwargs):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            return process

        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   side_effect=launch):
            with self.assertRaises(BackupProcessInterruptedError) as raised:
                run_monitored_command(["simulation"])
        self.assertEqual(raised.exception.reason, "interrupted")
        self.assertEqual(raised.exception.signal_number, signal.SIGTERM)
        process.terminate.assert_called_once()

    def test_exit_between_poll_and_signal_is_benign(self):
        process = MagicMock()
        process.poll.side_effect = [None, None, 0, 0]
        process.terminate.side_effect = ProcessLookupError()
        process.wait.return_value = 0
        self.assertTrue(_stop_process(process))

    def test_stop_escalates_with_bounded_waits(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch("iphone_backup_cli.backup_process._wait_stopped",
                   side_effect=[False, True]) as wait:
            self.assertTrue(_stop_process(process, stop_timeout=0.2, kill_timeout=0.3))
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(wait.call_args_list[0].args, (process, None, 0.2))
        self.assertEqual(wait.call_args_list[1].args, (process, None, 0.3))

    def test_cleanup_uncertainty_does_not_replace_original_failure(self):
        process = MagicMock()
        process.wait.return_value = 7
        process.poll.return_value = 7
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process), patch(
                       "iphone_backup_cli.backup_process._stop_process",
                       return_value=False):
            with self.assertRaises(BackupProcessError) as raised:
                run_monitored_command(["simulation"])
        self.assertEqual(raised.exception.reason, "exit")
        self.assertEqual(raised.exception.returncode, 7)
        self.assertTrue(raised.exception.cleanup_failed)

    def test_cleanup_os_errors_preserve_storage_failure_and_attempt_group_kill(self):
        for failure in ("poll", "wait", "kill"):
            with self.subTest(failure=failure):
                process = MagicMock(pid=12345)
                original = StorageUnavailableError("original SSD failure")
                checks = iter([None, original])

                def health():
                    value = next(checks)
                    if value is not None:
                        raise value

                process.poll.return_value = None
                if failure == "poll":
                    process.poll.side_effect = OSError("poll failed")
                elif failure == "wait":
                    process.wait.side_effect = OSError("wait failed")
                else:
                    process.kill.side_effect = OSError("kill failed")
                    process.wait.side_effect = OSError("wait failed")
                with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                           return_value=process), patch(
                               "iphone_backup_cli.backup_process.os.killpg",
                               side_effect=OSError("group signal failed")
                               if failure == "kill" else None) as kill:
                    with self.assertRaises(StorageUnavailableError) as raised:
                        run_monitored_command(["simulation"], health_check=health,
                                              kill_timeout=0.2)
                self.assertIs(raised.exception, original)
                self.assertTrue(original.cleanup_failed)
                self.assertIn(((12345, signal.SIGKILL), {}), kill.call_args_list)
                self.assertEqual(process.wait.call_args_list[-1].kwargs["timeout"], 0.2)

    def test_cleanup_poll_error_cannot_mask_original_process_failure(self):
        process = MagicMock()
        process.wait.side_effect = [7, 0]
        process.poll.side_effect = OSError("poll failed")
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process):
            with self.assertRaises(BackupProcessError) as raised:
                run_monitored_command(["simulation"], kill_timeout=0.2)
        self.assertEqual(raised.exception.reason, "exit")
        self.assertEqual(raised.exception.returncode, 7)
        self.assertTrue(raised.exception.cleanup_failed)
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_args_list[-1].kwargs["timeout"], 0.2)

    def test_group_cleanup_attempted_after_leader_already_exited(self):
        process = MagicMock(pid=12345)
        process.poll.return_value = 0
        with patch("iphone_backup_cli.backup_process._group_exists",
                   side_effect=[True, False]), patch(
                       "iphone_backup_cli.backup_process.os.killpg") as kill:
            self.assertTrue(_stop_process(process, group=12345))
        kill.assert_called_once_with(12345, signal.SIGTERM)
        process.wait.assert_called_once()


if __name__ == "__main__":
    unittest.main()
