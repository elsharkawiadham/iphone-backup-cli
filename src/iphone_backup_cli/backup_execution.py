import sys

from .backup_command import build_backup_command
from .backup_process import run_monitored_command
from .execution_preflight import prepare_backup_execution
from .storage import verify_storage
from .storage_identity import check_destination_identity


def simulate_backup_execution(destination, mount_point, volume_uuid, device_id):
    """Legacy read-only device preflight plus a Python no-op; never a transfer."""
    with prepare_backup_execution(
        destination, mount_point, volume_uuid, device_id, include_context=True,
    ) as prepared:
        # Do not recapture here: that would accept a replacement directory
        # while the operation still held the lock in the original directory.
        def check_storage():
            verify_storage(destination, mount_point, volume_uuid)
            check_destination_identity(prepared.identity)
            prepared.lock.check()

        check_storage()
        build_backup_command(device_id, destination)
        return run_monitored_command(
            [sys.executable, "-c", "pass"], timeout=10,
            health_check=check_storage, check_interval=1.0,
        )
