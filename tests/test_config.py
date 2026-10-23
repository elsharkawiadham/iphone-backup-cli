import errno
import json
import os
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
        # ExFAT accepts chmod but reports its mount-wide synthetic mode.
        # Compare with a private-mode probe on this same filesystem.
        probe = config.APP_DIR / ".permission-probe"
        probe.write_bytes(b"")
        probe.chmod(0o600)
        self.assertEqual(
            config.CONFIG_FILE.stat().st_mode & 0o777,
            probe.stat().st_mode & 0o777,
        )

    def test_refuse_overwrite(self):
        settings = {"backup_destination": "/Volumes/TestDrive"}

        config.save_config(settings)

        with self.assertRaises(FileExistsError):
            config.save_config({"backup_destination": "/OtherDrive"})

        self.assertEqual(config.load_config(), settings)

    def test_unsupported_hardlinks_use_exclusive_fallback(self):
        with patch.object(config.os, "link", side_effect=OSError(errno.ENOTSUP, "fixture")):
            config.save_config({"external": "SSD"})
        self.assertEqual(config.load_config(), {"external": "SSD"})
        self.assertEqual(list(config.APP_DIR.glob(".config-*.tmp")), [])

    def test_unimplemented_hardlinks_use_exclusive_fallback(self):
        with patch.object(config.os, "link", side_effect=OSError(errno.ENOSYS, "fixture")):
            config.save_config({"external": "SSD"})
        self.assertEqual(config.load_config(), {"external": "SSD"})

    def test_fallback_refuses_existing_file(self):
        config.APP_DIR.mkdir()
        original = b'{"existing": true}'
        config.CONFIG_FILE.write_bytes(original)
        with patch.object(config.os, "link", side_effect=OSError(errno.ENOTSUP, "fixture")):
            with self.assertRaises(FileExistsError):
                config.save_config({"replacement": True})
        self.assertEqual(config.CONFIG_FILE.read_bytes(), original)

    def test_fallback_refuses_existing_directory(self):
        config.CONFIG_FILE.mkdir(parents=True)
        sentinel = config.CONFIG_FILE / "keep.txt"
        sentinel.write_text("fixture sentinel")
        with patch.object(config.os, "link", side_effect=OSError(errno.ENOTSUP, "fixture")):
            with self.assertRaises(FileExistsError):
                config.save_config({"replacement": True})
        self.assertEqual(sentinel.read_text(), "fixture sentinel")

    def test_fallback_open_is_exclusive_and_does_not_follow_symlinks(self):
        actual_open = os.open
        with patch.object(config.os, "link", side_effect=OSError(errno.ENOTSUP, "fixture")):
            with patch.object(config.os, "open", wraps=actual_open) as opened:
                config.save_config({"external": "SSD"})
        call = next(call for call in opened.call_args_list if call.args[0] == config.CONFIG_FILE)
        self.assertTrue(call.args[1] & os.O_EXCL)
        self.assertTrue(call.args[1] & os.O_CREAT)
        if hasattr(os, "O_NOFOLLOW"):
            self.assertTrue(call.args[1] & os.O_NOFOLLOW)
        self.assertEqual(call.args[2], 0o600)

    def test_link_failures_do_not_relax_publication(self):
        for code in (errno.EACCES, errno.EIO, errno.EROFS, errno.EXDEV, errno.EEXIST):
            with self.subTest(code=code):
                with patch.object(config.os, "link", side_effect=OSError(code, "fixture")):
                    with patch.object(config, "_publish_exclusively") as fallback:
                        with self.assertRaises(OSError):
                            config.save_config({"external": "SSD"})
                fallback.assert_not_called()
                self.assertFalse(config.CONFIG_FILE.exists())
                self.assertEqual(list(config.APP_DIR.glob(".config-*.tmp")), [])

    def test_serialization_failure_publishes_nothing(self):
        with patch.object(config.os, "link") as link:
            with self.assertRaises(TypeError):
                config.save_config({"unsupported": object()})
        link.assert_not_called()
        self.assertFalse(config.CONFIG_FILE.exists())
        self.assertEqual(list(config.APP_DIR.glob(".config-*.tmp")), [])

    def test_partial_fallback_copy_remains_blocking_and_unloadable(self):
        partial = b'{"backup_destination":'

        def interrupted_copy(source, destination):
            destination.write(partial)
            raise OSError(errno.EIO, "disposable interrupted-copy fixture")

        with patch.object(config.os, "link", side_effect=OSError(errno.ENOTSUP, "fixture")):
            with patch.object(config.shutil, "copyfileobj", side_effect=interrupted_copy):
                with self.assertRaises(OSError):
                    config.save_config({"backup_destination": "/fixture"})
            self.assertEqual(config.CONFIG_FILE.read_bytes(), partial)
            with self.assertRaises(json.JSONDecodeError):
                config.load_config()
            with self.assertRaises(FileExistsError):
                config.save_config({"replacement": True})
        self.assertEqual(config.CONFIG_FILE.read_bytes(), partial)
        self.assertEqual(list(config.APP_DIR.glob(".config-*.tmp")), [])

    def test_failed_copy_does_not_unlink_replacement_config(self):
        replacement = b'{"other_writer": true}'

        def replaced_copy(source, destination):
            destination.write(b'{"incomplete":')
            destination.flush()
            config.CONFIG_FILE.unlink()
            config.CONFIG_FILE.write_bytes(replacement)
            raise OSError(errno.EIO, "disposable replacement fixture")

        with patch.object(config.os, "link", side_effect=OSError(errno.ENOTSUP, "fixture")):
            with patch.object(config.shutil, "copyfileobj", side_effect=replaced_copy):
                with self.assertRaises(OSError):
                    config.save_config({"backup_destination": "/fixture"})
        self.assertEqual(config.CONFIG_FILE.read_bytes(), replacement)

    def test_failed_fallback_sync_never_removes_or_overwrites_config(self):
        with patch.object(config.os, "link", side_effect=OSError(errno.ENOTSUP, "fixture")):
            with patch.object(config.os, "fsync", side_effect=[None, OSError(errno.EIO, "fixture")]):
                with self.assertRaises(OSError):
                    config.save_config({"backup_destination": "/fixture"})
            retained = config.CONFIG_FILE.read_bytes()
            self.assertTrue(retained)
            with self.assertRaises(FileExistsError):
                config.save_config({"replacement": True})
        self.assertEqual(config.CONFIG_FILE.read_bytes(), retained)


if __name__ == "__main__":
    unittest.main()
