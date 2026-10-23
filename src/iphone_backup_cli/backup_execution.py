import sys

from .backup_command import build_backup_command
from .backup_process import run_monitored_command
from .execution_preflight import prepare_backup_execution
from .storage import verify_storage
from .storage_identity import (
    capture_destination_identity,
    check_destination_identity,
)


def simulate_backup_execution(
    destination,
    mount_point,
    volume_uuid,
    device_id,
):
    """Exercise the guarded workflow without transferring device data."""

    with prepare_backup_execution(
        destination,
        mount_point,
        volume_uuid,
        device_id,
    ):
        identity = capture_destination_identity(
            destination,
            mount_point,
        )

        build_backup_command(device_id, destination)

        simulation = [
            sys.executable,
            "-c",
            "pass",
        ]

        def check_storage():
            verify_storage(destination, mount_point, volume_uuid)
            check_destination_identity(identity)

        return run_monitored_command(
            simulation,
            timeout=10,
            health_check=check_storage,
            check_interval=1.0,
        )
