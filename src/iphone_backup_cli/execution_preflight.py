from contextlib import contextmanager

from .backup_lock import acquire_backup_lock
from .backup_target import check_new_backup_target
from .encryption import verify_backup_encryption
from .storage import verify_storage


@contextmanager
def prepare_backup_execution(
    destination,
    mount_point,
    volume_uuid,
    device_id,
):
    """Validate and lock storage before a backup operation."""

    verify_storage(destination, mount_point, volume_uuid)

    with acquire_backup_lock(destination):
        verify_storage(destination, mount_point, volume_uuid)
        verify_backup_encryption(device_id)

        target = check_new_backup_target(destination, device_id)

        yield target
