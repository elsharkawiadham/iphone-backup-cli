from contextlib import contextmanager

from .backup_lock import acquire_backup_lock
from .backup_target import check_new_backup_target
from .encryption import verify_backup_encryption
from .storage import verify_storage
from .storage_identity import (
    capture_destination_identity,
    check_destination_identity,
)


@contextmanager
def prepare_backup_execution(
    destination,
    mount_point,
    volume_uuid,
    device_id,
):
    """Validate and lock storage before a backup operation."""

    # Capture before UUID verification so a volume swap between checks
    # cannot become the identity accepted by the writable lock open.
    identity = capture_destination_identity(destination, mount_point)
    verify_storage(destination, mount_point, volume_uuid)
    check_destination_identity(identity)

    with acquire_backup_lock(
        destination,
        expected_signature=identity.destination_signature,
    ):
        verify_storage(destination, mount_point, volume_uuid)
        check_destination_identity(identity)
        verify_backup_encryption(device_id)

        target = check_new_backup_target(destination, device_id)
        check_destination_identity(identity)

        yield target
