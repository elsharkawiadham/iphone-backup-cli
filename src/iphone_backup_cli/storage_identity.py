import os
from dataclasses import dataclass
from pathlib import Path

from .storage import StorageUnavailableError


@dataclass(frozen=True)
class DestinationIdentity:
    mount: Path
    destination: Path
    mount_signature: tuple
    destination_signature: tuple


def _inspect(mount, destination):
    try:
        if (
            mount.is_symlink()
            or destination.is_symlink()
            or not os.path.ismount(mount)
        ):
            raise StorageUnavailableError(
                "Expected destination mount is unavailable or unsafe."
            )

        resolved_mount = mount.resolve(strict=True)
        resolved_destination = destination.resolve(strict=True)

        # Keep checks tied to the exact paths later used by the process.
        # Resolving away an ancestor symlink would hide later redirection.
        if resolved_mount != mount or resolved_destination != destination:
            raise StorageUnavailableError(
                "Storage paths must be canonical and contain no symlinks."
            )

        if (
            resolved_destination == resolved_mount
            or not resolved_destination.is_relative_to(resolved_mount)
            or not resolved_destination.is_dir()
        ):
            raise StorageUnavailableError(
                "Backup destination is outside the expected mount."
            )

        mount_stat = mount.stat()
        destination_stat = destination.stat()

    except (OSError, RuntimeError) as error:
        raise StorageUnavailableError(
            "Backup destination identity is unavailable."
        ) from error

    if mount_stat.st_dev != destination_stat.st_dev:
        raise StorageUnavailableError(
            "Backup destination filesystem does not match the mount."
        )

    return (
        resolved_mount,
        resolved_destination,
        (mount_stat.st_dev, mount_stat.st_ino),
        (destination_stat.st_dev, destination_stat.st_ino),
    )


def capture_destination_identity(destination, mount_point):
    """Capture the verified directory's filesystem identity."""
    mount = Path(mount_point).expanduser()
    target = Path(destination).expanduser()

    if not mount.is_absolute() or not target.is_absolute():
        raise StorageUnavailableError(
            "Storage paths must be absolute."
        )

    return DestinationIdentity(
        *_inspect(mount, target)
    )


def check_destination_identity(identity):
    """Fail if the original mounted destination has changed."""
    if not isinstance(identity, DestinationIdentity):
        raise StorageUnavailableError(
            "Missing destination identity."
        )

    current = _inspect(identity.mount, identity.destination)

    if current != (
        identity.mount,
        identity.destination,
        identity.mount_signature,
        identity.destination_signature,
    ):
        raise StorageUnavailableError(
            "Backup destination identity changed."
        )

    return True
