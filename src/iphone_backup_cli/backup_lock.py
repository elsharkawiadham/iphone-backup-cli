import fcntl
import os
import stat
from contextlib import contextmanager
from pathlib import Path


class BackupLockError(Exception):
    """The backup destination cannot be locked safely."""


@contextmanager
def acquire_backup_lock(backup_root):
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

    lock_path = root / ".iphone-backup-cli.lock"

    try:
        fd = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
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
