"""Build a contained real-backup plan without executing it."""

import re
from dataclasses import dataclass
from pathlib import Path

from .backup_command import build_backup_command
from .backup_sandbox import prepare_sandboxed_command
from .backup_target import check_new_backup_target
from .storage import StorageUnavailableError, verify_storage
from .storage_identity import (
    capture_destination_identity,
    check_destination_identity,
)


IDEVICEBACKUP2 = Path("/opt/homebrew/bin/idevicebackup2")


@dataclass(frozen=True)
class RealBackupPlan:
    command: tuple[str, ...]
    cwd: Path
    target: Path
    root_identity: object
    operation_identity: object


def prepare_real_backup_plan(
    backup_root,
    operation_directory,
    mount_point,
    volume_uuid,
    device_id,
):
    """Prepare only. The caller must hold the backup lock."""

    root = Path(backup_root).expanduser()
    operation = Path(operation_directory).expanduser()

    if (
        not root.is_absolute()
        or not operation.is_absolute()
        or root.is_symlink()
        or operation.is_symlink()
    ):
        raise ValueError("Invalid backup operation paths.")

    if not re.fullmatch(
        r"\.iphone-backup-operation-[0-9a-f]{32}",
        operation.name,
    ):
        raise ValueError("Invalid backup operation directory name.")

    if operation.parent != root:
        raise ValueError("Operation must be directly inside backup root.")

    verify_storage(root, mount_point, volume_uuid)
    verify_storage(operation, mount_point, volume_uuid)

    root_identity = capture_destination_identity(root, mount_point)
    operation_identity = capture_destination_identity(
        operation, mount_point
    )

    check_destination_identity(root_identity)
    check_destination_identity(operation_identity)

    target = check_new_backup_target(operation, device_id)

    if not IDEVICEBACKUP2.is_file():
        raise StorageUnavailableError(
            "idevicebackup2 executable is unavailable."
        )

    original_command = build_backup_command(
        device_id, str(operation)
    )

    original_command[0] = str(IDEVICEBACKUP2)
    original_command[-1] = "."

    sandbox_command, cwd = prepare_sandboxed_command(
        original_command,
        operation,
    )

    if cwd != operation.resolve(strict=True):
        raise ValueError("Sandbox working directory mismatch.")

    return RealBackupPlan(
        command=tuple(sandbox_command),
        cwd=cwd,
        target=target,
        root_identity=root_identity,
        operation_identity=operation_identity,
    )
