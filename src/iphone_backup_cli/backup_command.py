from pathlib import Path


def build_backup_command(device_id, destination, full=False):
    """Build an idevicebackup2 command without executing it."""
    if (
        not isinstance(device_id, str)
        or not device_id.strip()
        or device_id != device_id.strip()
        or device_id.startswith("-")
    ):
        raise ValueError("Invalid device identifier.")

    if not isinstance(full, bool):
        raise ValueError("Full backup option must be a boolean.")

    directory = Path(destination).expanduser()

    if not directory.is_absolute():
        raise ValueError("Backup destination must be absolute.")

    directory = directory.resolve(strict=True)

    if not directory.is_dir():
        raise ValueError("Backup destination must be a directory.")

    command = [
        "idevicebackup2",
        "-u",
        device_id,
        "-i",
        "backup",
    ]

    if full:
        command.append("--full")

    command.append(str(directory))
    return command
