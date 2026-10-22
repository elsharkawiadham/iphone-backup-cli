import io
import unittest
from contextlib import redirect_stdout
from subprocess import CalledProcessError
from unittest.mock import patch

from iphone_backup_cli.doctor import run_doctor


class TestDoctor(unittest.TestCase):

    @patch("iphone_backup_cli.doctor.list_connected_devices")
    @patch("iphone_backup_cli.doctor.shutil.which")
    @patch("iphone_backup_cli.doctor.platform.system")
    def test_device_detection_failure(
        self, mock_system, mock_which, mock_devices
    ):
        mock_system.return_value = "Darwin"
        mock_which.return_value = "/usr/local/bin/tool"

        mock_devices.side_effect = CalledProcessError(
            1, ["idevice_id", "-l"]
        )

        output = io.StringIO()

        with redirect_stdout(output):
            result = run_doctor()

        self.assertEqual(result, 1)
        self.assertIn(
            "RESULT: Diagnostics incomplete",
            output.getvalue()
        )

    @patch("iphone_backup_cli.doctor.list_connected_devices")
    @patch("iphone_backup_cli.doctor.shutil.which")
    @patch("iphone_backup_cli.doctor.platform.system")
    def test_no_connected_devices(
        self, mock_system, mock_which, mock_devices
    ):
        mock_system.return_value = "Darwin"
        mock_which.return_value = "/usr/local/bin/tool"
        mock_devices.return_value = []

        with redirect_stdout(io.StringIO()):
            result = run_doctor()

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
