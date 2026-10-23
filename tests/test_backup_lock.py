import fcntl
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import (
    BackupLockError,
    BackupLockGuard,
    QUARANTINE_NAME,
    acquire_backup_lock,
)


class TestBackupLock(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_lock_acquired(self):
        with acquire_backup_lock(self.root):
            self.assertTrue(
                (self.root / ".iphone-backup-cli.lock").is_file()
            )

    def test_second_operation_rejected(self):
        with acquire_backup_lock(self.root):
            with self.assertRaisesRegex(
                BackupLockError, "already running"
            ):
                with acquire_backup_lock(self.root):
                    pass

    def test_lock_released_after_operation(self):
        with acquire_backup_lock(self.root):
            pass

        with acquire_backup_lock(self.root):
            pass

    def test_lock_released_after_exception(self):
        with self.assertRaisesRegex(RuntimeError, "Simulated failure"):
            with acquire_backup_lock(self.root):
                raise RuntimeError("Simulated failure")

        with acquire_backup_lock(self.root):
            pass

    def test_symlink_lock_rejected(self):
        lock = self.root / ".iphone-backup-cli.lock"
        lock.symlink_to(self.root / "missing")

        with self.assertRaises(BackupLockError):
            with acquire_backup_lock(self.root):
                pass


    def test_replaced_root_rejected_before_lock_creation(self):
        destination = self.root / "Backups"
        previous = self.root / "PreviousBackups"
        destination.mkdir()
        original_stat = destination.stat()
        signature = (original_stat.st_dev, original_stat.st_ino)
        original_open = os.open
        replaced = False

        def replace_before_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is None and Path(path) == destination:
                destination.rename(previous)
                destination.mkdir()
                replaced = True
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with patch(
            "iphone_backup_cli.backup_lock.os.open",
            side_effect=replace_before_open,
        ):
            with self.assertRaises(BackupLockError):
                with acquire_backup_lock(
                    destination,
                    expected_signature=signature,
                ):
                    self.fail("Replaced destination was accepted.")

        self.assertTrue(replaced)
        self.assertFalse((destination / ".iphone-backup-cli.lock").exists())
        self.assertFalse((previous / ".iphone-backup-cli.lock").exists())

    def test_lock_open_pins_directory_and_rejects_replacement(self):
        destination = self.root / "Backups"
        previous = self.root / "PreviousBackups"
        destination.mkdir()
        original_stat = destination.stat()
        signature = (original_stat.st_dev, original_stat.st_ino)
        original_open = os.open
        replaced = False

        def replace_before_lock(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal replaced
            if dir_fd is not None and path == ".iphone-backup-cli.lock":
                destination.rename(previous)
                destination.mkdir()
                replaced = True
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with patch(
            "iphone_backup_cli.backup_lock.os.open",
            side_effect=replace_before_lock,
        ):
            with self.assertRaisesRegex(BackupLockError, "identity changed"):
                with acquire_backup_lock(
                    destination,
                    expected_signature=signature,
                ):
                    self.fail("Replaced destination was accepted.")

            self.assertTrue(replaced)
            self.assertTrue((previous / ".iphone-backup-cli.lock").is_file())
            self.assertFalse((destination / ".iphone-backup-cli.lock").exists())

        self.assertFalse((destination / ".iphone-backup-cli.lock").exists())



    def test_yielded_guard_pins_directory_and_closes_descriptors(self):
        with acquire_backup_lock(self.root) as guard:
            self.assertIsInstance(guard, BackupLockGuard)
            self.assertEqual(os.fstat(guard.root_fd).st_ino, self.root.stat().st_ino)
            self.assertTrue(guard.check())

        for descriptor in (guard.root_fd, guard.lock_fd):
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_existing_lock_contents_are_preserved(self):
        lock = self.root / ".iphone-backup-cli.lock"
        contents = b"Existing lock contents must remain unchanged."
        lock.write_bytes(contents)
        signature = lock.stat().st_ino
        with acquire_backup_lock(self.root):
            self.assertEqual(lock.read_bytes(), contents)
        self.assertEqual(lock.read_bytes(), contents)
        self.assertEqual(lock.stat().st_ino, signature)

    def test_fifo_lock_is_rejected_without_opening_it(self):
        lock = self.root / ".iphone-backup-cli.lock"
        # ExFAT cannot create FIFOs. Model its metadata around a disposable
        # file so the fail-closed pre-open path is tested on every filesystem.
        lock.touch()
        original_stat = os.stat
        original_open = os.open

        def fifo_metadata(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == ".iphone-backup-cli.lock" and kwargs.get("dir_fd") is not None:
                values = list(result)
                values[0] = stat.S_IFIFO | 0o600
                return os.stat_result(values)
            return result

        def inspect_open(path, flags, mode=0o777, *, dir_fd=None):
            if dir_fd is not None and not flags & os.O_EXCL:
                self.fail("Existing FIFO was opened before validation.")
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with (
            patch("iphone_backup_cli.backup_lock.os.stat", side_effect=fifo_metadata),
            patch("iphone_backup_cli.backup_lock.os.open", side_effect=inspect_open),
        ):
            with self.assertRaisesRegex(BackupLockError, "regular file"):
                with acquire_backup_lock(self.root):
                    pass
        self.assertTrue(lock.exists())

    def test_directory_lock_is_rejected(self):
        (self.root / ".iphone-backup-cli.lock").mkdir()
        with self.assertRaisesRegex(BackupLockError, "regular file"):
            with acquire_backup_lock(self.root):
                pass

    def test_hardlinked_lock_is_rejected(self):
        lock = self.root / ".iphone-backup-cli.lock"
        lock.write_bytes(b"Preserve this file.")
        original_stat = os.stat

        def linked_metadata(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == ".iphone-backup-cli.lock" and kwargs.get("dir_fd") is not None:
                values = list(result)
                values[3] = 2
                return os.stat_result(values)
            return result

        with patch("iphone_backup_cli.backup_lock.os.stat", side_effect=linked_metadata):
            with self.assertRaisesRegex(BackupLockError, "one link"):
                with acquire_backup_lock(self.root):
                    pass
        self.assertEqual(lock.read_bytes(), b"Preserve this file.")

    def test_guard_detects_lock_replacement(self):
        lock = self.root / ".iphone-backup-cli.lock"
        with acquire_backup_lock(self.root) as guard:
            lock.rename(self.root / "previous-lock")
            lock.write_bytes(b"Replacement")
            with self.assertRaisesRegex(BackupLockError, "identity changed"):
                guard.check()
        self.assertEqual(lock.read_bytes(), b"Replacement")

    def test_guard_detects_lock_removal(self):
        with acquire_backup_lock(self.root) as guard:
            (self.root / ".iphone-backup-cli.lock").unlink()
            with self.assertRaises(BackupLockError):
                guard.check()
        self.assertFalse((self.root / ".iphone-backup-cli.lock").exists())

    def test_guard_detects_added_hardlink(self):
        with acquire_backup_lock(self.root) as guard:
            original_fstat = os.fstat

            def linked_metadata(fd):
                result = original_fstat(fd)
                if fd == guard.lock_fd:
                    values = list(result)
                    values[3] = 2
                    return os.stat_result(values)
                return result

            with patch("iphone_backup_cli.backup_lock.os.fstat", side_effect=linked_metadata):
                with self.assertRaisesRegex(BackupLockError, "one link"):
                    guard.check()

    def test_guard_detects_replaced_root(self):
        destination = self.root / "Backups"
        destination.mkdir()
        with acquire_backup_lock(destination) as guard:
            destination.rename(self.root / "Original")
            destination.mkdir()
            with self.assertRaisesRegex(BackupLockError, "identity changed"):
                guard.check()
        self.assertEqual(list(destination.iterdir()), [])

    def test_guard_detects_ancestor_symlink_redirection(self):
        parent = self.root / "parent"
        destination = parent / "Backups"
        destination.mkdir(parents=True)
        with acquire_backup_lock(destination) as guard:
            original = self.root / "original"
            parent.rename(original)
            parent.symlink_to(original, target_is_directory=True)
            with self.assertRaisesRegex(BackupLockError, "identity changed"):
                guard.check()

    def test_ancestor_symlink_is_rejected_before_creating_lock(self):
        original = self.root / "original"
        original.mkdir()
        (original / "Backups").mkdir()
        alias = self.root / "alias"
        alias.symlink_to(original, target_is_directory=True)
        with self.assertRaisesRegex(BackupLockError, "canonical"):
            with acquire_backup_lock(alias / "Backups"):
                pass
        self.assertFalse((original / "Backups" / ".iphone-backup-cli.lock").exists())

    def test_lock_replacement_after_inspection_is_rejected(self):
        lock = self.root / ".iphone-backup-cli.lock"
        lock.write_bytes(b"Original")
        original_open = os.open

        def replace_before_existing_open(path, flags, mode=0o777, *, dir_fd=None):
            if dir_fd is not None and not flags & os.O_EXCL:
                lock.rename(self.root / "original-lock")
                lock.write_bytes(b"Replacement")
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with patch(
            "iphone_backup_cli.backup_lock.os.open",
            side_effect=replace_before_existing_open,
        ):
            with self.assertRaisesRegex(BackupLockError, "identity changed"):
                with acquire_backup_lock(self.root):
                    pass
        self.assertEqual(lock.read_bytes(), b"Replacement")
        self.assertEqual((self.root / "original-lock").read_bytes(), b"Original")

    def test_lock_replacement_during_flock_is_rejected(self):
        lock = self.root / ".iphone-backup-cli.lock"
        original_flock = fcntl.flock

        def replace_during_flock(fd, operation):
            result = original_flock(fd, operation)
            if operation == fcntl.LOCK_EX | fcntl.LOCK_NB:
                lock.rename(self.root / "original-lock")
                lock.write_bytes(b"Replacement")
            return result

        with patch(
            "iphone_backup_cli.backup_lock.fcntl.flock",
            side_effect=replace_during_flock,
        ):
            with self.assertRaisesRegex(BackupLockError, "identity changed"):
                with acquire_backup_lock(self.root):
                    pass
        self.assertEqual(lock.read_bytes(), b"Replacement")



    def test_cleanup_quarantine_blocks_new_operations_without_auto_clear(self):
        with acquire_backup_lock(self.root) as guard:
            self.assertTrue(guard.quarantine("operation-123"))
            self.assertTrue(guard.check())
        marker = self.root / QUARANTINE_NAME
        original = marker.read_bytes()
        self.assertIn(b"operation-123", original)
        for _ in range(2):
            with self.assertRaisesRegex(BackupLockError, "Manual inspection"):
                with acquire_backup_lock(self.root):
                    self.fail("Quarantined operation was accepted.")
            self.assertEqual(marker.read_bytes(), original)

    def test_cleanup_quarantine_never_overwrites_existing_marker(self):
        marker = self.root / QUARANTINE_NAME
        with acquire_backup_lock(self.root) as guard:
            marker.write_bytes(b"Existing safety information")
            signature = marker.stat().st_ino
            self.assertFalse(guard.quarantine("new-operation"))
            self.assertTrue(guard.check())
        self.assertEqual(marker.read_bytes(), b"Existing safety information")
        self.assertEqual(marker.stat().st_ino, signature)

    def test_cleanup_quarantine_preserves_symlink_and_its_target(self):
        target = self.root / "personal-file"
        target.write_bytes(b"Preserve personal data")
        marker = self.root / QUARANTINE_NAME
        with acquire_backup_lock(self.root) as guard:
            marker.symlink_to(target)
            self.assertFalse(guard.quarantine("operation"))
        self.assertTrue(marker.is_symlink())
        self.assertEqual(target.read_bytes(), b"Preserve personal data")
        with self.assertRaisesRegex(BackupLockError, "Manual inspection"):
            with acquire_backup_lock(self.root):
                pass

    def test_cleanup_quarantine_uses_pinned_directory_after_redirection(self):
        destination = self.root / "Backups"
        destination.mkdir()
        previous = self.root / "Original"
        original_open = os.open
        with acquire_backup_lock(destination) as guard:
            def redirect_before_marker(path, flags, mode=0o777, *, dir_fd=None):
                if path == QUARANTINE_NAME:
                    self.assertEqual(dir_fd, guard.root_fd)
                    self.assertTrue(flags & os.O_EXCL)
                    self.assertTrue(flags & os.O_NOFOLLOW)
                    destination.rename(previous)
                    destination.mkdir()
                return original_open(path, flags, mode, dir_fd=dir_fd)

            with patch(
                "iphone_backup_cli.backup_lock.os.open",
                side_effect=redirect_before_marker,
            ):
                self.assertTrue(guard.quarantine("operation"))
        self.assertTrue((previous / QUARANTINE_NAME).is_file())
        self.assertEqual(list(destination.iterdir()), [])

    def test_failed_cleanup_marker_write_still_blocks_new_operations(self):
        with acquire_backup_lock(self.root) as guard:
            with patch("iphone_backup_cli.backup_lock.os.write", side_effect=OSError("SSD I/O")):
                with self.assertRaisesRegex(BackupLockError, "manual inspection"):
                    guard.quarantine("operation")
        self.assertTrue((self.root / QUARANTINE_NAME).is_file())
        with self.assertRaisesRegex(BackupLockError, "Manual inspection"):
            with acquire_backup_lock(self.root):
                pass

    def test_invalid_quarantine_operation_name_creates_nothing(self):
        with acquire_backup_lock(self.root) as guard:
            for name in ("../unsafe", "a\nb", "", ".", "..", None):
                with self.assertRaisesRegex(BackupLockError, "Invalid quarantine"):
                    guard.quarantine(name)
        self.assertFalse((self.root / QUARANTINE_NAME).exists())

    def test_directory_cleanup_marker_is_also_a_barrier(self):
        marker = self.root / QUARANTINE_NAME
        marker.mkdir()
        with self.assertRaisesRegex(BackupLockError, "Manual inspection"):
            with acquire_backup_lock(self.root):
                pass
        self.assertTrue(marker.is_dir())


if __name__ == "__main__":
    unittest.main()
