import subprocess
import unittest
from unittest.mock import MagicMock, Mock, patch

from iphone_backup_cli.backup_process import run_monitored_command
from iphone_backup_cli.storage import StorageUnavailableError


class TestBackupHealthMonitor(unittest.TestCase):

    def test_initial_storage_failure_prevents_process_start(self):
        check = Mock(side_effect=StorageUnavailableError("SSD unavailable before start"))
        with patch("iphone_backup_cli.backup_process.subprocess.Popen") as start:
            with self.assertRaises(StorageUnavailableError):
                run_monitored_command(["simulation"], health_check=check)
        check.assert_called_once_with()
        start.assert_not_called()

    def test_storage_checked_repeatedly(self):
        process = MagicMock()
        process.wait.side_effect = [
            subprocess.TimeoutExpired(["simulation"], 0.01), 0,
        ]
        check = Mock()
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process):
            self.assertEqual(run_monitored_command(
                ["simulation"], health_check=check, check_interval=0.01,
            ), 0)
        self.assertEqual(check.call_count, 4)

    def test_storage_failure_stops_process(self):
        process = MagicMock()
        process.poll.side_effect = [None, None, 0, 0]
        process.wait.side_effect = [
            subprocess.TimeoutExpired(["simulation"], 0.01), 0,
        ]
        check = Mock(side_effect=[
            None, None, StorageUnavailableError("SSD disconnected"),
        ])
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process):
            with self.assertRaises(StorageUnavailableError):
                run_monitored_command(
                    ["simulation"], health_check=check, check_interval=0.01,
                )
        self.assertEqual(check.call_count, 3)
        self.assertEqual(process.wait.call_count, 2)
        process.terminate.assert_called_once()

    def test_storage_failure_after_process_exit(self):
        process = MagicMock()
        process.wait.return_value = 0
        check = Mock(side_effect=[
            None, None, StorageUnavailableError("SSD unavailable at completion"),
        ])
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process):
            with self.assertRaises(StorageUnavailableError):
                run_monitored_command(["simulation"], health_check=check)
        self.assertEqual(check.call_count, 3)
        process.wait.assert_called_once()
        process.terminate.assert_not_called()

    def test_final_health_failure_also_cleans_up_descendants(self):
        process = MagicMock(pid=12345)
        process.wait.return_value = 0
        check = Mock(side_effect=[
            None, None, StorageUnavailableError("SSD redirected at completion"),
        ])
        with patch("iphone_backup_cli.backup_process.subprocess.Popen",
                   return_value=process), patch(
                       "iphone_backup_cli.backup_process._stop_process",
                       return_value=True) as stop:
            with self.assertRaises(StorageUnavailableError):
                run_monitored_command(["simulation"], health_check=check)
        stop.assert_called_once_with(process, 12345, 1.0, 1.0)

    def test_invalid_health_interval_rejected(self):
        with self.assertRaises(ValueError):
            run_monitored_command(
                ["simulation"], health_check=lambda: None, check_interval=0,
            )


if __name__ == "__main__":
    unittest.main()
