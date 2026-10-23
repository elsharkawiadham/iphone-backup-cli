"""Guarded real-backup planning only. Never executes a transfer."""

from contextlib import contextmanager

from .execution_preflight import prepare_backup_execution
from .real_backup_plan import prepare_real_backup_plan
from .storage_identity import check_destination_identity


@contextmanager
def guarded_real_backup_plan(
    backup_root,
    operation_directory,
    mount_point,
    volume_uuid,
    device_id,
):
    """Keep the backup lock active while validating a real-backup plan."""

    with prepare_backup_execution(
        backup_root,
        mount_point,
        volume_uuid,
        device_id,
    ):
        plan = prepare_real_backup_plan(
            backup_root,
            operation_directory,
            mount_point,
            volume_uuid,
            device_id,
        )

        if any(plan.cwd.iterdir()):
            raise ValueError(
                "Backup operation directory must be empty."
            )

        check_destination_identity(plan.root_identity)
        check_destination_identity(plan.operation_identity)

        yield plan
