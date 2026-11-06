"""Non-executing handoff after fresh backup safety verification.

This module never launches commands or authorizes real transfers.
"""

from dataclasses import dataclass
from pathlib import Path

from .backup_sandbox import USBMUX_SANDBOX_PROFILE
from .real_backup_plan import IDEVICEBACKUP2

from .prelaunch_safety import require_fresh_prelaunch_safety


@dataclass(frozen=True)
class CheckedLaunchIntent:
    command: tuple[str, ...]
    cwd: Path


def prepare_checked_launch_intent(
    prepared, backup_root, mount_point, volume_uuid, device_id
):
    """Validate an existing plan without executing its command."""

    if prepared.state != "planned_only":
        raise ValueError("Operation is not in planned-only state.")

    plan = prepared.plan
    path = prepared.path
    lock = prepared.lock

    command = plan.command
    cwd = plan.cwd
    target = plan.target
    root_identity = plan.root_identity
    operation_identity = plan.operation_identity

    if (
        not isinstance(command, tuple)
        or not command
        or not all(isinstance(arg, str) and arg for arg in command)
    ):
        raise ValueError("Invalid planned command.")

    if (
        not isinstance(path, Path)
        or not isinstance(cwd, Path)
        or not path.is_absolute()
        or cwd != path
        or Path(backup_root) != path.parent
    ):
        raise ValueError("Invalid planned directories.")

    expected_command = (
        "/usr/bin/sandbox-exec",
        "-D",
        f"WRITABLE_ROOT={cwd}",
        "-p",
        USBMUX_SANDBOX_PROFILE,
        str(IDEVICEBACKUP2),
        "-u",
        device_id,
        "backup",
        ".",
    )

    if command != expected_command:
        raise ValueError("Unexpected planned backup command.")

    if require_fresh_prelaunch_safety(
        prepared, backup_root, mount_point, volume_uuid, device_id
    ) is not True:
        raise ValueError("Prelaunch safety was not confirmed.")

    if (
        prepared.plan is not plan
        or prepared.path != path
        or prepared.lock is not lock
        or plan.command != command
        or plan.cwd != cwd
        or plan.target != target
        or plan.root_identity is not root_identity
        or plan.operation_identity is not operation_identity
    ):
        raise ValueError("Backup plan changed during verification.")

    return CheckedLaunchIntent(command=command, cwd=cwd)
