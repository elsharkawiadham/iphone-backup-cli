import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import patch

from iphone_backup_cli.storage import (
    StorageUnavailableError,
    verify_storage,
    identify_volume,
)


class TestStorage(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.root = Path(temp.name).resolve()
        self.mount = self.root / "volume"
        self.destination = self.mount / "backups"
        self.destination.mkdir(parents=True)

    def mock_diskutil(self, uuid="test-uuid"):
        return CompletedProcess(
            args=["diskutil"],
            returncode=0,
            stdout=plistlib.dumps({
                **({"VolumeUUID": uuid} if uuid is not None else {}),
                "MountPoint": str(self.mount),
                "Internal": False,
                "Writable": True,
                "WritableVolume": True,
                "WritableMedia": True,
            }),
            stderr=b"",
        )

    def check(self, destination=None):
        return verify_storage(
            destination=destination or self.destination,
            mount_point=self.mount,
            expected_uuid="test-uuid",
        )

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_valid_storage(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil()

        self.assertTrue(self.check())

    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_disconnected_storage(self, mock_mount):
        mock_mount.return_value = False

        with self.assertRaises(StorageUnavailableError):
            self.check()

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_wrong_uuid(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil("wrong-uuid")

        with self.assertRaises(StorageUnavailableError):
            self.check()

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_outside_volume(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil()

        outside = self.root / "outside"
        outside.mkdir()

        with self.assertRaises(StorageUnavailableError):
            self.check(outside)

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_missing_destination(self, mock_mount, mock_run):
        mock_mount.return_value = True
        mock_run.return_value = self.mock_diskutil()

        with self.assertRaises(StorageUnavailableError):
            self.check(self.mount / "missing")


    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_identify_valid_volume(self, mock_mount, mock_run):
        mock_mount.side_effect = lambda p: Path(p) == self.mount
        mock_run.return_value = self.mock_diskutil()

        result = identify_volume(self.destination)

        self.assertEqual(result["mount_point"], str(self.mount))
        self.assertEqual(result["volume_uuid"], "test-uuid")

    def test_identify_missing_directory(self):
        with self.assertRaises(StorageUnavailableError):
            identify_volume(self.root / "missing")

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_identify_missing_uuid(self, mock_mount, mock_run):
        mock_mount.side_effect = lambda p: Path(p) == self.mount
        mock_run.return_value = self.mock_diskutil(uuid=None)

        with self.assertRaises(StorageUnavailableError):
            identify_volume(self.destination)

    @patch("iphone_backup_cli.storage.subprocess.run")
    @patch("iphone_backup_cli.storage.os.path.ismount")
    def test_identify_wrong_mount_point(self, mock_mount, mock_run):
        mock_mount.side_effect = lambda p: Path(p) == self.mount

        mock_run.return_value = CompletedProcess(
            args=["diskutil"],
            returncode=0,
            stdout=plistlib.dumps({
                "VolumeUUID": "test-uuid",
                "MountPoint": str(self.root),
            }),
            stderr=b"",
        )

        with self.assertRaises(StorageUnavailableError):
            identify_volume(self.destination)


class TestExternalVolumeRequirement(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.mount = self.root / "volume"
        self.destination = self.mount / "backups"
        self.destination.mkdir(parents=True)

    def identify_with_internal_value(self, internal):
        info = {
            "VolumeUUID": "test-uuid",
            "MountPoint": str(self.mount),
            "Writable": True,
            "WritableVolume": True,
            "WritableMedia": True,
        }

        if internal is not None:
            info["Internal"] = internal

        result = CompletedProcess(
            args=["diskutil"],
            returncode=0,
            stdout=plistlib.dumps(info),
            stderr=b"",
        )

        with patch(
            "iphone_backup_cli.storage.os.path.ismount",
            side_effect=lambda path: Path(path) == self.mount,
        ), patch(
            "iphone_backup_cli.storage.subprocess.run",
            return_value=result,
        ):
            return identify_volume(
                self.destination,
                require_external=True,
            )

    def test_external_volume_accepted(self):
        result = self.identify_with_internal_value(False)
        self.assertEqual(result["volume_uuid"], "test-uuid")

    def test_internal_volume_rejected(self):
        with self.assertRaisesRegex(
            StorageUnavailableError, "confirmed external"
        ):
            self.identify_with_internal_value(True)

    def test_unknown_volume_type_rejected(self):
        with self.assertRaisesRegex(
            StorageUnavailableError, "confirmed external"
        ):
            self.identify_with_internal_value(None)


class TestAdversarialStorage(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.mount = self.root / "volume"
        self.destination = self.mount / "backups"
        self.destination.mkdir(parents=True)
        self.info = {
            "VolumeUUID": "test-uuid",
            "MountPoint": str(self.mount),
            "Internal": False,
            "Writable": True,
            "WritableVolume": True,
            "WritableMedia": True,
        }
        mount_patch = patch(
            "iphone_backup_cli.storage.os.path.ismount",
            side_effect=lambda path: Path(path) == self.mount,
        )
        run_patch = patch("iphone_backup_cli.storage.subprocess.run")
        self.mock_mount = mount_patch.start()
        self.mock_run = run_patch.start()
        self.addCleanup(mount_patch.stop)
        self.addCleanup(run_patch.stop)
        self.mock_run.side_effect = lambda *args, **kwargs: CompletedProcess(
            ["diskutil"], 0, plistlib.dumps(self.info), b""
        )

    def check(self, destination=None, mount_point=None, expected_uuid="test-uuid"):
        return verify_storage(
            destination=self.destination if destination is None else destination,
            mount_point=self.mount if mount_point is None else mount_point,
            expected_uuid=expected_uuid,
        )

    def check_both(self):
        for operation in (self.check, lambda: identify_volume(self.destination)):
            with self.subTest(operation=operation):
                with self.assertRaises(StorageUnavailableError):
                    operation()

    def test_valid_storage_uses_bounded_diskutil_lookup(self):
        self.assertTrue(self.check())
        self.mock_run.assert_called_once_with(
            ["diskutil", "info", "-plist", str(self.mount)],
            capture_output=True, check=True, timeout=15,
        )

    def test_invalid_expected_uuid(self):
        for value in (None, "", 1, False, ["test-uuid"]):
            with self.subTest(value=value):
                with self.assertRaises(StorageUnavailableError):
                    self.check(expected_uuid=value)

    def test_mount_root_destination_rejected(self):
        with self.assertRaises(StorageUnavailableError):
            self.check(self.mount)

    def test_sibling_with_volume_prefix_rejected(self):
        sibling = self.root / "volume-other"
        sibling.mkdir()
        with self.assertRaises(StorageUnavailableError):
            self.check(sibling)

    def test_file_destination_rejected(self):
        target = self.mount / "file"
        target.write_text("fixture")
        with self.assertRaises(StorageUnavailableError):
            self.check(target)
        with self.assertRaises(StorageUnavailableError):
            identify_volume(target)

    def test_invalid_uuid_metadata_rejected(self):
        for value in (None, "", 0, False, [], {}, " test-uuid "):
            with self.subTest(value=value):
                if value is None:
                    self.info.pop("VolumeUUID", None)
                else:
                    self.info["VolumeUUID"] = value
                self.check_both()

    def test_invalid_mount_metadata_rejected(self):
        for value in (None, "", 1, False, [], {}, "relative", str(self.root)):
            with self.subTest(value=value):
                if value is None:
                    self.info.pop("MountPoint", None)
                else:
                    self.info["MountPoint"] = value
                self.check_both()

    def test_external_volume_required_for_verify(self):
        for value in (None, True, 0, "false", []):
            with self.subTest(value=value):
                if value is None:
                    self.info.pop("Internal", None)
                else:
                    self.info["Internal"] = value
                with self.assertRaisesRegex(
                    StorageUnavailableError, "confirmed external"
                ):
                    self.check()

    def test_identify_can_inspect_internal_volume_when_external_not_required(self):
        self.info["Internal"] = True
        self.assertEqual(
            identify_volume(self.destination)["volume_uuid"], "test-uuid"
        )

    def test_unconfirmed_writable_volume_rejected(self):
        for value in (None, False, 1, "true", []):
            with self.subTest(value=value):
                if value is None:
                    self.info.pop("Writable", None)
                else:
                    self.info["Writable"] = value
                self.check_both()

    def test_contradictory_optional_metadata_rejected(self):
        for key in ("WritableVolume", "WritableMedia", "Mounted"):
            for value in (False, 1, "true", []):
                with self.subTest(key=key, value=value):
                    self.info[key] = value
                    self.check_both()
            self.info[key] = True

    def test_missing_optional_metadata_accepted(self):
        self.info.pop("WritableVolume")
        self.info.pop("WritableMedia")
        self.assertTrue(self.check())

    def test_explicit_mounted_true_accepted(self):
        self.info["Mounted"] = True
        self.assertTrue(self.check())

    def test_non_dict_plist_rejected(self):
        for value in ([], "volume", False, 1, b"metadata"):
            with self.subTest(value=value):
                self.mock_run.side_effect = None
                self.mock_run.return_value = CompletedProcess(
                    ["diskutil"], 0, plistlib.dumps(value)
                )
                self.check_both()

    def test_malformed_plist_rejected(self):
        for value in (
            b"not a plist", b"<?xml version='1.0'?><plist><dict>", None, "text"
        ):
            with self.subTest(value=value):
                self.mock_run.side_effect = None
                self.mock_run.return_value = CompletedProcess(["diskutil"], 0, value)
                self.check_both()

    def test_diskutil_failures_rejected(self):
        for error in (
            subprocess.CalledProcessError(1, ["diskutil"]),
            subprocess.TimeoutExpired(["diskutil"], 15),
            OSError("disk unavailable"),
        ):
            with self.subTest(error=error):
                self.mock_run.side_effect = error
                self.check_both()

    def test_relative_paths_rejected(self):
        with self.assertRaises(StorageUnavailableError):
            self.check(destination="relative")
        with self.assertRaises(StorageUnavailableError):
            self.check(mount_point="relative")
        with self.assertRaises(StorageUnavailableError):
            identify_volume("relative")
        self.mock_run.assert_not_called()

    def test_parent_traversal_rejected_even_when_resolving_inside_volume(self):
        target = str(self.mount / "backups" / ".." / "backups")
        with self.assertRaises(StorageUnavailableError):
            self.check(target)
        with self.assertRaises(StorageUnavailableError):
            identify_volume(target)
        with self.assertRaises(StorageUnavailableError):
            self.check(mount_point=str(self.mount / "backups" / ".."))
        self.mock_run.assert_not_called()

    @staticmethod
    def simulate_symlink(alias, target):
        # ExFAT cannot create symlinks. Model the resolver's observed
        # redirection while keeping every disposable fixture on the SSD.
        actual_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path.is_relative_to(alias):
                return target / path.relative_to(alias)
            return actual_resolve(path, *args, **kwargs)

        return patch("iphone_backup_cli.storage.Path.resolve", resolve)

    def test_symlink_destination_and_ancestor_rejected(self):
        link = self.mount / "link"
        with self.simulate_symlink(link, self.destination):
            for target in (link, link / "nested"):
                with self.subTest(target=target):
                    with self.assertRaises(StorageUnavailableError):
                        self.check(target)
                    with self.assertRaises(StorageUnavailableError):
                        identify_volume(target)
        self.mock_run.assert_not_called()

    def test_symlink_mount_rejected(self):
        link = self.root / "link-volume"
        with self.simulate_symlink(link, self.mount):
            with self.assertRaises(StorageUnavailableError):
                self.check(link / "backups", mount_point=link)
        self.mock_run.assert_not_called()

    def test_symlink_reported_mount_rejected(self):
        link = self.root / "link-volume"
        self.info["MountPoint"] = str(link)
        with self.simulate_symlink(link, self.mount):
            self.check_both()

    def test_symlink_loop_rejected(self):
        loop = self.mount / "loop"
        actual_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path == loop:
                raise RuntimeError("Symlink loop in disposable fixture")
            return actual_resolve(path, *args, **kwargs)

        with patch("iphone_backup_cli.storage.Path.resolve", resolve):
            with self.assertRaises(StorageUnavailableError):
                self.check(loop)
            with self.assertRaises(StorageUnavailableError):
                identify_volume(loop)

    def test_nested_filesystem_rejected(self):
        actual_stat = Path.stat

        def stat(path, *args, **kwargs):
            value = actual_stat(path, *args, **kwargs)
            if path == self.destination:
                return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev + 1)
            return value

        with patch("iphone_backup_cli.storage.Path.stat", stat):
            self.check_both()

    def test_stat_failure_rejected(self):
        actual_stat = Path.stat
        def stat(path, *args, **kwargs):
            if path == self.destination:
                raise OSError("fixture disappeared")
            return actual_stat(path, *args, **kwargs)

        with patch("iphone_backup_cli.storage.Path.stat", stat):
            with self.assertRaises(StorageUnavailableError):
                self.check()


if __name__ == "__main__":
    unittest.main()
