import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli import config
from iphone_backup_cli import setup


class TestSetup(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.backups = self.root / "backups"
        self.photos = self.root / "photos"

        self.backups.mkdir()
        self.photos.mkdir()

        app_dir = self.root / "app"
        config_file = app_dir / "config.json"

        for module, name, value in [
            (config, "APP_DIR", app_dir),
            (config, "CONFIG_FILE", config_file),
            (setup, "CONFIG_FILE", config_file),
        ]:
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        volume = {
            "mount_point": "/Volumes/TestSSD",
            "volume_uuid": "test-uuid",
        }

        for name, value in [
            ("identify_volume", volume),
            ("verify_storage", True),
        ]:
            patcher = patch.object(setup, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_backup_only(self):
        with patch(
            "builtins.input",
            side_effect=[str(self.backups), "n"],
        ):
            result = setup.run_setup()

        self.assertEqual(result, 0)

        saved = config.load_config()
        self.assertEqual(
            saved["backup_destination"],
            str(self.backups.resolve()),
        )
        self.assertFalse(saved["photo_archive_enabled"])

    def test_backup_and_photos(self):
        with patch(
            "builtins.input",
            side_effect=[
                str(self.backups),
                "y",
                str(self.photos),
            ],
        ):
            result = setup.run_setup()

        self.assertEqual(result, 0)
        self.assertEqual(
            config.load_config()["photo_destination"],
            str(self.photos.resolve()),
        )

    def test_invalid_destination(self):
        with patch(
            "builtins.input",
            return_value=str(self.root / "missing"),
        ):
            result = setup.run_setup()

        self.assertEqual(result, 1)
        self.assertIsNone(config.load_config())

    def test_existing_configuration(self):
        config.save_config({"existing": True})

        result = setup.run_setup()

        self.assertEqual(result, 1)
        self.assertEqual(
            config.load_config(),
            {"existing": True},
        )

    def test_same_destination_rejected(self):
        with patch(
            "builtins.input",
            side_effect=[
                str(self.backups),
                "y",
                str(self.backups),
            ],
        ):
            result = setup.run_setup()

        self.assertEqual(result, 1)
        self.assertIsNone(config.load_config())


    def test_nonempty_destination_rejected(self):
        (self.backups / "existing.txt").write_text("Important data")

        with self.assertRaisesRegex(ValueError, "must be empty"):
            setup.validate_destination(str(self.backups))

    def test_drive_root_rejected(self):
        with self.assertRaisesRegex(ValueError, "dedicated subdirectory"):
            setup.validate_destination("/")

    def test_home_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, "dedicated subdirectory"):
            setup.validate_destination(str(Path.home()))

    def test_finder_backup_subdirectory_rejected(self):
        destination = self.root / "MobileSync_Backup" / "new"
        destination.mkdir(parents=True)

        with self.assertRaisesRegex(ValueError, "Finder backup"):
            setup.validate_destination(str(destination))


    def test_backup_volume_identity_saved(self):
        with patch(
            "builtins.input",
            side_effect=[str(self.backups), "n"],
        ):
            result = setup.run_setup()

        self.assertEqual(result, 0)

        saved = config.load_config()
        self.assertEqual(
            saved["backup_volume"],
            {
                "mount_point": "/Volumes/TestSSD",
                "volume_uuid": "test-uuid",
            },
        )

    def test_photo_volume_identity_saved(self):
        with patch(
            "builtins.input",
            side_effect=[str(self.backups), "y", str(self.photos)],
        ):
            result = setup.run_setup()

        self.assertEqual(result, 0)

        saved = config.load_config()
        self.assertEqual(
            saved["photo_volume"],
            {
                "mount_point": "/Volumes/TestSSD",
                "volume_uuid": "test-uuid",
            },
        )

    def test_backup_storage_verification_failure(self):
        with patch.object(
            setup,
            "verify_storage",
            side_effect=setup.StorageUnavailableError("Wrong volume"),
        ):
            with patch(
                "builtins.input",
                side_effect=[str(self.backups), "n"],
            ):
                result = setup.run_setup()

        self.assertEqual(result, 1)
        self.assertIsNone(config.load_config())

    def test_photo_storage_verification_failure(self):
        with patch.object(
            setup,
            "verify_storage",
            side_effect=[
                True,
                setup.StorageUnavailableError("Wrong photo volume"),
            ],
        ):
            with patch(
                "builtins.input",
                side_effect=[str(self.backups), "y", str(self.photos)],
            ):
                result = setup.run_setup()

        self.assertEqual(result, 1)
        self.assertIsNone(config.load_config())


if __name__ == "__main__":
    unittest.main()
