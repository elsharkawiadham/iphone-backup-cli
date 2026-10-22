import os
import plistlib
import subprocess
from pathlib import Path


class StorageUnavailableError(Exception):
    """The configured storage volume is unavailable or unsafe."""


def verify_storage(destination, mount_point, expected_uuid):
    mount = Path(mount_point).expanduser()

    if not os.path.ismount(mount):
        raise StorageUnavailableError(
            "Expected storage volume is not mounted."
        )

    try:
        result = subprocess.run(
            ["diskutil", "info", "-plist", str(mount)],
            capture_output=True,
            check=True,
            timeout=15,
        )
        info = plistlib.loads(result.stdout)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
        ValueError,
    ) as error:
        raise StorageUnavailableError(
            "Unable to verify storage volume identity."
        ) from error

    if info.get("VolumeUUID") != expected_uuid:
        raise StorageUnavailableError(
            "Storage volume UUID does not match."
        )

    reported_mount = info.get("MountPoint")

    if not reported_mount or Path(reported_mount).resolve() != mount.resolve():
        raise StorageUnavailableError(
            "Storage mount point does not match."
        )

    try:
        target = Path(destination).expanduser().resolve(strict=True)
        resolved_mount = mount.resolve(strict=True)
    except OSError as error:
        raise StorageUnavailableError(
            "Storage destination is unavailable."
        ) from error

    if not target.is_dir():
        raise StorageUnavailableError(
            "Storage destination is not a directory."
        )

    if target == resolved_mount or not target.is_relative_to(resolved_mount):
        raise StorageUnavailableError(
            "Destination must be inside the configured volume."
        )

    return True


def identify_volume(destination, require_external=False):
    """Identify the mounted filesystem containing a directory."""
    try:
        target = Path(destination).expanduser().resolve(strict=True)
    except OSError as error:
        raise StorageUnavailableError(
            "Destination does not exist or is inaccessible."
        ) from error

    if not target.is_dir():
        raise StorageUnavailableError(
            "Destination must be a directory."
        )

    mount = target
    while not os.path.ismount(mount):
        if mount == mount.parent:
            raise StorageUnavailableError(
                "Could not identify the mounted volume."
            )
        mount = mount.parent

    try:
        result = subprocess.run(
            ["diskutil", "info", "-plist", str(mount)],
            capture_output=True,
            check=True,
            timeout=15,
        )
        info = plistlib.loads(result.stdout)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
        ValueError,
    ) as error:
        raise StorageUnavailableError(
            "Could not retrieve volume identity."
        ) from error

    if require_external and info.get("Internal") is not False:
        raise StorageUnavailableError(
            "Destination must be on a confirmed external volume."
        )

    uuid = info.get("VolumeUUID")
    reported_mount = info.get("MountPoint")

    if not uuid or not reported_mount:
        raise StorageUnavailableError(
            "Volume UUID or mount point is unavailable."
        )

    if Path(reported_mount).resolve() != mount.resolve():
        raise StorageUnavailableError(
            "Reported mount point does not match."
        )

    return {
        "mount_point": str(mount),
        "volume_uuid": str(uuid),
    }
