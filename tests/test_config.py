import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli import config


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        app_dir = Path(self.temp.name) / "ApplicationSupport"
        config_file = app_dir / "config.json"

        patcher_dir = patch.object(config, "APP_DIR", app_dir)
        patcher_file = patch.object(config, "CONFIG_FILE", config_file)

        patcher_dir.start()
        patcher_file.start()

        self.addCleanup(patcher_dir.stop)
        self.addCleanup(patcher_file.stop)

    def test_missing_config(self):
        self.assertIsNone(config.load_config())

    def test_save_and_load(self):
        settings = {
            "backup_destination": "/Volumes/TestDrive/Backups",
            "photo_archive_enabled": False,
        }

        config.save_config(settings)

        self.assertEqual(config.load_config(), settings)
        self.assertEqual(
            config.CONFIG_FILE.stat().st_mode & 0o777,
            0o600,
        )

    def test_refuse_overwrite(self):
        settings = {"backup_destination": "/Volumes/TestDrive"}

        config.save_config(settings)

        with self.assertRaises(FileExistsError):
            config.save_config({"backup_destination": "/OtherDrive"})

        self.assertEqual(config.load_config(), settings)


if __name__ == "__main__":
    unittest.main()
