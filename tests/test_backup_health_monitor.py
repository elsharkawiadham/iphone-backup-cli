import subprocess
import unittest
from unittest.mock import MagicMock, Mock, patch

from iphone_backup_cli.backup_process import run_monitored_command
from iphone_backup_cli.storage import StorageUnavailableError


class TestBackupHealthMonitor(unittest.TestCase):

    def test_storage_checked_repeatedly(self):
        process = MagicMock()
        process.wait.side_effect = [
            subprocess.TimeoutExpired(["simulation"], 0.01),
            0,
        ]

        check = Mock()

        with patch(
            "iphone_backup_cli.backup_process.subprocess.Popen",
            return_value=process,
        ):
            result = run_monitored_command(
                ["simulation"],
                health_check=check,
                check_interval=0.01,
            )

        self.assertEqual(result, 0)
        self.assertEqual(check.call_count, 3)

    def test_storage_failure_stops_process(self):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired(["simulation"], 0.01),
            0,
        ]

        check = Mock(
            side_effect=[
                None,
                StorageUnavailableError("SSD disconnected"),
            ]
        )

        with patch(
            "iphone_backup_cli.backup_process.subprocess.Popen",
            return_value=process,
        ):
            with self.assertRaises(StorageUnavailableError):
                run_monitored_command(
                    ["simulation"],
                    health_check=check,
                    check_interval=0.01,
                )

        process.terminate.assert_called_once()


    def test_storage_failure_after_process_exit(self):
        process = MagicMock()
        process.wait.return_value = 0

        check = Mock(
            side_effect=[
                None,
                StorageUnavailableError("SSD unavailable at completion"),
            ]
        )

        with patch(
            "iphone_backup_cli.backup_process.subprocess.Popen",
            return_value=process,
        ):
            with self.assertRaises(StorageUnavailableError):
                run_monitored_command(
                    ["simulation"],
                    health_check=check,
                )

        self.assertEqual(check.call_count, 3)


    def test_storage_failure_after_process_exit(self):
        process = MagicMock()
        process.wait.return_value = 0

        check = Mock(
            side_effect=[
                None,
                StorageUnavailableError("SSD unavailable at completion"),
            ]
        )

        with patch(
            "iphone_backup_cli.backup_process.subprocess.Popen",
            return_value=process,
        ):
            with self.assertRaises(StorageUnavailableError):
                run_monitored_command(
                    ["simulation"],
                    health_check=check,
                )

        self.assertEqual(check.call_count, 2)

    def test_invalid_health_interval_rejected(self):
        with self.assertRaises(ValueError):
            run_monitored_command(
                ["simulation"],
                health_check=lambda: None,
                check_interval=0,
            )


if __name__ == "__main__":
    unittest.main()
