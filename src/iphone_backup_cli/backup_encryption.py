"""Read-only, fail-closed iPhone backup encryption check."""

import subprocess
from pathlib import Path

from .backup_process import _minimal_child_environment
from .backup_sandbox import prepare_sandboxed_command

IDEVICEINFO = Path("/opt/homebrew/bin/ideviceinfo")


class BackupEncryptionError(RuntimeError):
    """Device encryption could not be safely confirmed."""


def require_backup_encryption(device_id, writable_directory):
    """Confirm encryption without changing iPhone settings."""

    if (
        not isinstance(device_id, str)
        or not device_id.strip()
        or device_id != device_id.strip()
        or device_id.startswith("-")
        or chr(0) in device_id
    ):
        raise BackupEncryptionError("Invalid device identifier.")

    if not IDEVICEINFO.is_file():
        raise BackupEncryptionError("Device information tool unavailable.")

    query = [
        str(IDEVICEINFO),
        "-u", device_id,
        "--domain", "com.apple.mobile.backup",
        "--key", "WillEncrypt",
    ]

    try:
        command, cwd = prepare_sandboxed_command(
            query,
            writable_directory,
            allow_usbmux=True,
        )

        result = subprocess.run(
            command,
            cwd=cwd,
            env=_minimal_child_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BackupEncryptionError(
            "Cannot verify backup encryption."
        ) from error

    if result.returncode != 0:
        raise BackupEncryptionError(
            "Device encryption query failed."
        )

    value = result.stdout.strip().lower()

    if value in ("true", "1"):
        return True

    if value in ("false", "0"):
        raise BackupEncryptionError(
            "Encrypted local backups are disabled."
        )

    raise BackupEncryptionError(
        "Backup encryption status is unknown."
    )
