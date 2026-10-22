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
