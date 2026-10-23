import os
import plistlib
import subprocess
from pathlib import Path
from xml.parsers.expat import ExpatError


class StorageUnavailableError(Exception):
    """The configured storage volume is unavailable or unsafe."""


def _directory(value):
    """Inspect the exact absolute path that later filesystem calls will use."""
    try:
        path = Path(value).expanduser()
        if not path.is_absolute() or ".." in path.parts:
            raise StorageUnavailableError(
                "Storage paths must be absolute and canonical."
            )
        if path.resolve(strict=True) != path:
            raise StorageUnavailableError(
                "Storage paths must be canonical and contain no symlinks."
            )
        if not path.is_dir():
            raise StorageUnavailableError(
                "Storage destination is not a directory."
            )
        return path
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise StorageUnavailableError(
            "Storage destination is unavailable."
        ) from error


def _volume_info(mount, require_external):
    try:
        if not os.path.ismount(mount):
            raise StorageUnavailableError(
                "Expected storage volume is not mounted."
            )
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
        TypeError,
        OverflowError,
        ExpatError,
    ) as error:
        raise StorageUnavailableError(
            "Unable to verify storage volume identity."
        ) from error

    if not isinstance(info, dict):
        raise StorageUnavailableError("Invalid storage volume metadata.")

    if require_external and info.get("Internal") is not False:
        raise StorageUnavailableError(
            "Destination must be on a confirmed external volume."
        )

    # Current macOS reports a MountPoint but no Mounted key. Reject an
    # explicit contradictory Mounted value when a version supplies it.
    if "Mounted" in info and info["Mounted"] is not True:
        raise StorageUnavailableError("Storage volume is not mounted.")

    if info.get("Writable") is not True or any(
        key in info and info[key] is not True
        for key in ("WritableVolume", "WritableMedia")
    ):
        raise StorageUnavailableError(
            "Storage volume is not confirmed writable."
        )

    uuid = info.get("VolumeUUID")
    reported_mount = info.get("MountPoint")
    if not isinstance(uuid, str) or not uuid or uuid.strip() != uuid:
        raise StorageUnavailableError("Volume UUID is unavailable or invalid.")
    if not isinstance(reported_mount, str) or not reported_mount:
        raise StorageUnavailableError("Volume mount point is unavailable.")
    if _directory(reported_mount) != mount:
        raise StorageUnavailableError("Storage mount point does not match.")

    return info


def _check_same_filesystem(mount, target):
    try:
        if mount.stat().st_dev != target.stat().st_dev:
            raise StorageUnavailableError(
                "Storage destination filesystem does not match the mount."
            )
    except OSError as error:
        raise StorageUnavailableError(
            "Storage destination is unavailable."
        ) from error


def verify_storage(destination, mount_point, expected_uuid):
    """Check a canonical destination on the configured writable external SSD.

    These observations are a point-in-time check, not an atomic reservation
    of a path or a guarantee against a later unmount or directory replacement.
    """
    mount = _directory(mount_point)
    target = _directory(destination)
    info = _volume_info(mount, require_external=True)

    if (
        not isinstance(expected_uuid, str)
        or not expected_uuid
        or info["VolumeUUID"] != expected_uuid
    ):
        raise StorageUnavailableError("Storage volume UUID does not match.")

    if target == mount or not target.is_relative_to(mount):
        raise StorageUnavailableError(
            "Destination must be inside the configured volume."
        )
    _check_same_filesystem(mount, target)
    return True


def identify_volume(destination, require_external=False):
    """Identify the writable mounted filesystem containing a directory."""
    target = _directory(destination)
    mount = target
    try:
        while not os.path.ismount(mount):
            if mount == mount.parent:
                raise StorageUnavailableError(
                    "Could not identify the mounted volume."
                )
            mount = mount.parent
    except OSError as error:
        raise StorageUnavailableError(
            "Could not identify the mounted volume."
        ) from error

    info = _volume_info(mount, require_external=require_external)
    _check_same_filesystem(mount, target)
    return {
        "mount_point": str(mount),
        "volume_uuid": info["VolumeUUID"],
    }
