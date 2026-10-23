import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from iphone_backup_cli.backup_process import (
    BackupProcessError,
    run_monitored_command,
)


class TestBackupProcess(unittest.TestCase):

    def test_successful_process(self):
        result = run_monitored_command([
            sys.executable,
            "-c",
            "pass",
        ])
        self.assertEqual(result, 0)

    def test_nonzero_exit_rejected(self):
        with self.assertRaisesRegex(
            BackupProcessError, "code 7"
        ):
            run_monitored_command([
                sys.executable,
                "-c",
                "import sys; sys.exit(7)",
            ])

    def test_timeout_stops_process(self):
        with self.assertRaisesRegex(
            BackupProcessError, "timed out"
        ):
            run_monitored_command([
                sys.executable,
                "-c",
                "import time; time.sleep(5)",
            ], timeout=0.05)

    def test_invalid_command_rejected(self):
        with self.assertRaises(ValueError):
            run_monitored_command([])

    def test_interruption_stops_process(self):
        process = MagicMock()
        process.wait.side_effect = [
            KeyboardInterrupt(),
            0,
        ]
        process.poll.return_value = None

        with patch(
            "iphone_backup_cli.backup_process.subprocess.Popen",
            return_value=process,
        ):
            with self.assertRaises(KeyboardInterrupt):
                run_monitored_command(["test-command"])

        process.terminate.assert_called_once()

    def test_missing_executable_rejected(self):
        with self.assertRaises(BackupProcessError):
            run_monitored_command([
                "/nonexistent/iphone-backup-cli-test-program"
            ])


if __name__ == "__main__":
    unittest.main()
