from contextlib import contextmanager
from dataclasses import dataclass

from .backup_lock import acquire_backup_lock
from .backup_target import check_new_backup_target
from .encryption import verify_backup_encryption
from .storage import verify_storage
from .storage_identity import capture_destination_identity, check_destination_identity


@dataclass(frozen=True)
class PreparedExecution:
    target: object
    identity: object
    lock: object


@contextmanager
def prepare_backup_execution(
    destination, mount_point, volume_uuid, device_id, *, include_context=False,
):
    """Validate and lock storage, retaining the original identity throughout."""
    identity = capture_destination_identity(destination, mount_point)
    verify_storage(destination, mount_point, volume_uuid)
    check_destination_identity(identity)

    with acquire_backup_lock(
        destination, expected_signature=identity.destination_signature,
    ) as lock:
        verify_storage(destination, mount_point, volume_uuid)
        check_destination_identity(identity)
        lock.check()
        verify_backup_encryption(device_id)
        target = check_new_backup_target(destination, device_id)
        check_destination_identity(identity)
        lock.check()
        yield PreparedExecution(target, identity, lock) if include_context else target
