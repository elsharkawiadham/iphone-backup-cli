import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

from iphone_backup_cli.devices import list_connected_devices


class TestDeviceDetection(unittest.TestCase):

    @patch("iphone_backup_cli.devices.subprocess.run")
    def test_one_device(self, mock_run):
        mock_run.return_value = CompletedProcess(
            args=["idevice_id", "-l"],
            returncode=0,
            stdout="DEVICE123\n",
            stderr="",
        )

        devices = list_connected_devices()

        self.assertEqual(devices, ["DEVICE123"])

    @patch("iphone_backup_cli.devices.subprocess.run")
    def test_multiple_devices(self, mock_run):
        mock_run.return_value = CompletedProcess(
            args=["idevice_id", "-l"],
            returncode=0,
            stdout="DEVICE123\nDEVICE456\n",
            stderr="",
        )

        devices = list_connected_devices()

        self.assertEqual(
            devices,
            ["DEVICE123", "DEVICE456"],
        )

    @patch("iphone_backup_cli.devices.subprocess.run")
    def test_no_devices(self, mock_run):
        mock_run.return_value = CompletedProcess(
            args=["idevice_id", "-l"],
            returncode=0,
            stdout="",
            stderr="",
        )

        devices = list_connected_devices()

        self.assertEqual(devices, [])


if __name__ == "__main__":
    unittest.main()
