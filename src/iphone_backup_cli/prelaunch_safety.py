"""Fresh safety verification for a future real-backup launch.

This module never launches a backup or changes device settings.
"""

from .backup_encryption import BackupEncryptionError, require_backup_encryption
from .backup_target import check_new_backup_target
from .storage import verify_storage
from .storage_identity import check_destination_identity


def require_fresh_prelaunch_safety(
    prepared, backup_root, mount_point, volume_uuid, device_id
):
    """Fail closed unless all launch prerequisites remain valid."""

    def check_storage():
        verify_storage(backup_root, mount_point, volume_uuid)
        verify_storage(prepared.path, mount_point, volume_uuid)

        check_destination_identity(prepared.plan.root_identity)
        check_destination_identity(prepared.plan.operation_identity)

        prepared.lock.check()

        target = check_new_backup_target(
            prepared.path, device_id
        )

        if (
            target != prepared.plan.target
            or prepared.plan.cwd != prepared.path
        ):
            raise ValueError("Backup operation plan changed.")

    check_storage()

    # Fresh device query; never rely on a cached encryption result.
    if require_backup_encryption(device_id, prepared.path) is not True:
        raise BackupEncryptionError(
            "Backup encryption was not positively confirmed."
        )

    # Device communication takes time. Revalidate the SSD afterward.
    check_storage()

    return True
