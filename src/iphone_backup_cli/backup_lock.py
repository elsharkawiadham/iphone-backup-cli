import fcntl
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


LOCK_NAME = ".iphone-backup-cli.lock"
QUARANTINE_NAME = ".iphone-backup-cli.cleanup-unconfirmed"


class BackupLockError(Exception):
    """The backup destination cannot be locked safely."""


def _signature(value):
    return value.st_dev, value.st_ino


def _check_root(root, root_fd, signature):
    held = os.fstat(root_fd)
    current = os.stat(root, follow_symlinks=False)
    if (
        not stat.S_ISDIR(held.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or _signature(held) != signature
        or _signature(current) != signature
        or root.resolve(strict=True) != root
    ):
        raise BackupLockError("Backup directory identity changed.")


def _check_regular_lock(value):
    if not stat.S_ISREG(value.st_mode):
        raise BackupLockError("Backup lock is not a regular file.")
    if value.st_nlink != 1:
        raise BackupLockError("Backup lock must have exactly one link.")


def _reject_cleanup_quarantine(root_fd):
    try:
        os.stat(QUARANTINE_NAME, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise BackupLockError(
            "Could not inspect cleanup quarantine; manual inspection is required."
        ) from error
    raise BackupLockError(
        "Previous process cleanup is unconfirmed. Manual inspection of surviving "
        "processes and preserved output is required before clearing " + QUARANTINE_NAME + "."
    )


@dataclass(frozen=True)
class BackupLockGuard:
    """Pinned descriptors and advisory-lock ownership for one operation."""

    root: Path
    root_fd: int
    lock_fd: int
    root_signature: tuple
    lock_signature: tuple

    def check(self):
        """Reject removal, replacement, aliases, or a redirected root."""
        try:
            _check_root(self.root, self.root_fd, self.root_signature)
            held = os.fstat(self.lock_fd)
            current = os.stat(
                LOCK_NAME, dir_fd=self.root_fd, follow_symlinks=False
            )
            _check_regular_lock(held)
            _check_regular_lock(current)
            if (
                _signature(held) != self.lock_signature
                or _signature(current) != self.lock_signature
            ):
                raise BackupLockError("Backup lock identity changed.")
        except (OSError, RuntimeError) as error:
            raise BackupLockError("Backup lock or directory is unavailable.") from error
        return True


    def quarantine(self, operation_name):
        """Persist a manual-inspection barrier without replacing any marker.

        Writes stay on the pinned root even if its public pathname is redirected.
        A partial or existing marker remains a barrier; no automatic clearing is
        permitted. The current guard remains usable for final failure journaling.
        """
        if (
            not isinstance(operation_name, str)
            or operation_name in {".", ".."}
            or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", operation_name) is None
        ):
            raise BackupLockError("Invalid quarantine operation name.")
        message = (
            "Previous simulation process cleanup could not be confirmed.\n"
            "Operation: " + operation_name + "\n"
            "Inspect surviving processes and preserved output manually before "
            "clearing this marker. No automatic resume or deletion.\n"
        ).encode("ascii")
        try:
            held = os.fstat(self.root_fd)
            if not stat.S_ISDIR(held.st_mode) or _signature(held) != self.root_signature:
                raise BackupLockError("Backup directory identity changed.")
            try:
                fd = os.open(
                    QUARANTINE_NAME,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600, dir_fd=self.root_fd,
                )
            except FileExistsError:
                return False
            try:
                while message:
                    count = os.write(fd, message)
                    if count <= 0:
                        raise OSError("Cleanup marker write made no progress.")
                    message = message[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(self.root_fd)
        except OSError as error:
            raise BackupLockError(
                "Could not confirm cleanup quarantine; manual inspection is required."
            ) from error
        return True


@contextmanager
def acquire_backup_lock(backup_root, expected_signature=None):
    """Hold a checked lock; never truncate, replace, or delete its file.

    The yielded guard keeps the directory pinned for descriptor-relative writes.
    Its check must also run during execution: advisory locks cannot prevent an
    unrelated process from unlinking or replacing their directory entry.
    """
    root = Path(backup_root).expanduser()

    if not root.is_absolute() or root.is_symlink():
        raise BackupLockError("Invalid backup directory.")

    try:
        if root.resolve(strict=True) != root:
            raise BackupLockError("Backup directory must be canonical.")
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, RuntimeError) as error:
        raise BackupLockError("Could not open backup directory.") from error

    try:
        root_signature = _signature(os.fstat(root_fd))
        if expected_signature is not None and root_signature != expected_signature:
            raise BackupLockError("Backup directory identity changed.")
        try:
            _check_root(root, root_fd, root_signature)
        except (OSError, RuntimeError) as error:
            raise BackupLockError("Backup directory is unavailable.") from error

        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            try:
                fd = os.open(
                    LOCK_NAME, flags | os.O_CREAT | os.O_EXCL, 0o600,
                    dir_fd=root_fd,
                )
                previous = None
            except FileExistsError:
                # Inspect existing nodes before opening, and retain the inode
                # identity so replacement between inspection and open fails.
                previous = os.stat(
                    LOCK_NAME, dir_fd=root_fd, follow_symlinks=False
                )
                _check_regular_lock(previous)
                fd = os.open(LOCK_NAME, flags, dir_fd=root_fd)
        except OSError as error:
            raise BackupLockError("Could not open backup lock.") from error

        try:
            lock_stat = os.fstat(fd)
            _check_regular_lock(lock_stat)
            if previous is not None and _signature(previous) != _signature(lock_stat):
                raise BackupLockError("Backup lock identity changed.")
            guard = BackupLockGuard(
                root, root_fd, fd, root_signature, _signature(lock_stat)
            )
            guard.check()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise BackupLockError(
                    "Another backup operation is already running."
                ) from error
            except OSError as error:
                raise BackupLockError("Could not acquire backup lock.") from error

            try:
                guard.check()
                _reject_cleanup_quarantine(root_fd)
                yield guard
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)
