"""Fixed, sandboxed simulation after prelaunch verification.

Never executes the planned idevicebackup2 command. The prelaunch gate
still performs a read-only encryption query on the device; only the
supervised worker is device-free. Not connected to the public CLI.
"""

import sys
from dataclasses import dataclass

from .backup_lock import BackupLockError
from .backup_process import run_monitored_command
from .backup_sandbox import prepare_sandboxed_command
from .backup_target import check_new_backup_target
from .prelaunch_orchestration import prepare_checked_launch_intent
from .storage import verify_storage
from .storage_identity import check_destination_identity


# Fixed harmless worker: no files, no device access, no transfer.
_NOOP_WORKER = "pass"


@dataclass(frozen=True)
class SimulatedBoundaryResult:
    status: str
    exit_code: int
    transfer_started: bool = False
    backup_verified: bool = False


def run_checked_harmless_simulation(
    prepared, backup_root, mount_point, volume_uuid, device_id
):
    """Supervise only a fixed no-op, never the planned backup command."""

    intent = prepare_checked_launch_intent(
        prepared, backup_root, mount_point, volume_uuid, device_id
    )

    def check_health():
        verify_storage(backup_root, mount_point, volume_uuid)
        verify_storage(prepared.path, mount_point, volume_uuid)

        check_destination_identity(prepared.plan.root_identity)
        check_destination_identity(prepared.plan.operation_identity)

        prepared.lock.check()

        if (
            prepared.path != intent.cwd
            or prepared.plan.cwd != intent.cwd
            or check_new_backup_target(prepared.path, device_id)
            != prepared.plan.target
        ):
            raise ValueError("Simulation operation changed.")

    # The validated real-backup command is intentionally unused.
    # Only this fixed Python no-op can reach the process supervisor.
    simulated_command, cwd = prepare_sandboxed_command(
        [sys.executable, "-I", "-c", _NOOP_WORKER],
        prepared.path,
        allow_usbmux=False,
    )

    if cwd != intent.cwd:
        raise ValueError("Simulation working directory changed.")

    check_health()

    try:
        exit_code = run_monitored_command(
            simulated_command,
            cwd=cwd,
            health_check=check_health,
            check_interval=0.05,
            timeout=5.0,
        )
    except BaseException as error:
        if getattr(error, "cleanup_failed", False):
            try:
                prepared.lock.quarantine(prepared.path.name)
            except (BackupLockError, OSError) as quarantine_error:
                error.add_note(
                    "Quarantine could not be persisted: "
                    + str(quarantine_error)
                )
        raise

    if type(exit_code) is not int or exit_code != 0:
        raise ValueError("Simulated process did not report a clean exit.")

    check_health()

    return SimulatedBoundaryResult(
        status="simulation_succeeded",
        exit_code=exit_code,
    )
