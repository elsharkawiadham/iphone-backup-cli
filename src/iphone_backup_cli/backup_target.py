import re
from pathlib import Path


class BackupTargetError(Exception):
    """The proposed device backup directory is unsafe."""


def check_new_backup_target(backup_root, device_id):
    """Inspect a new device backup target without modifying files."""
    if (
        not isinstance(device_id, str)
        or re.fullmatch(r"[0-9a-fA-F-]{16,64}", device_id) is None
    ):
        raise BackupTargetError("Invalid device identifier.")

    root = Path(backup_root).expanduser()

    if not root.is_absolute() or root.is_symlink():
        raise BackupTargetError("Invalid backup root.")

    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise BackupTargetError(
            "Backup root is unavailable."
        ) from error

    if not root.is_dir():
        raise BackupTargetError(
            "Backup root must be a directory."
        )

    target = root / device_id

    if target.is_symlink() or target.exists():
        raise BackupTargetError(
            "A backup target already exists for this device."
        )

    return target
