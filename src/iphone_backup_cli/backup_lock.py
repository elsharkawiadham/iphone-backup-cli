import fcntl
import os
import stat
from contextlib import contextmanager
from pathlib import Path


class BackupLockError(Exception):
    """The backup destination cannot be locked safely."""


@contextmanager
def acquire_backup_lock(backup_root, expected_signature=None):
    """Hold an exclusive backup lock for the duration of an operation."""
    root = Path(backup_root).expanduser()

    if not root.is_absolute() or root.is_symlink():
        raise BackupLockError("Invalid backup directory.")

    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise BackupLockError("Backup directory is unavailable.") from error

    if not root.is_dir():
        raise BackupLockError("Backup destination is not a directory.")

    try:
        root_fd = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
    except OSError as error:
        raise BackupLockError("Could not open backup directory.") from error

    try:
        root_stat = os.fstat(root_fd)
        if expected_signature is not None and (
            root_stat.st_dev, root_stat.st_ino
        ) != expected_signature:
            raise BackupLockError("Backup directory identity changed.")

        # Pin the verified directory before any writable open. A replaced
        # pathname must never create a lock on a fallback filesystem.
        try:
            fd = os.open(
                ".iphone-backup-cli.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
                dir_fd=root_fd,
            )
        except OSError as error:
            raise BackupLockError("Could not open backup lock.") from error

        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise BackupLockError("Backup lock is not a regular file.")

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise BackupLockError(
                    "Another backup operation is already running."
                ) from error

            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)
