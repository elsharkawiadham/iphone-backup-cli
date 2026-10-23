"""Create guarded real-backup operation plans; never execute transfers."""

import json
import os
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .execution_preflight import prepare_backup_execution
from .real_backup_plan import prepare_real_backup_plan
from .storage import StorageUnavailableError, verify_storage
from .storage_identity import check_destination_identity


@dataclass(frozen=True)
class PreparedRealOperation:
    path: Path
    plan: object
    state: str = "planned_only"
    lock: object = None


def _write_planning_record(directory_fd):
    record = {
        "schema": 1,
        "kind": "real_backup_plan",
        "state": "planned_only",
        "transfer_started": False,
        "backup_verified": False,
    }

    encoded = (json.dumps(record, sort_keys=True) + "\n").encode()

    fd = os.open(
        "planning.json",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )

    try:
        while encoded:
            written = os.write(fd, encoded)
            if written <= 0:
                raise OSError("Planning journal write failed.")
            encoded = encoded[written:]

        os.fsync(fd)
    finally:
        os.close(fd)

    os.fsync(directory_fd)


@contextmanager
def create_guarded_real_operation(
    backup_root,
    mount_point,
    volume_uuid,
    device_id,
):
    """Allocate a unique operation under the original locked SSD root.

    No transfer is executed. Operation folders remain for inspection.
    """

    root = Path(backup_root).expanduser()

    with prepare_backup_execution(
        str(root),
        mount_point,
        volume_uuid,
        device_id,
        include_context=True,
    ) as protected:

        lock = protected.lock
        identity = protected.identity

        def check_root():
            verify_storage(str(root), mount_point, volume_uuid)
            check_destination_identity(identity)
            lock.check()

        check_root()

        name = ".iphone-backup-operation-" + uuid.uuid4().hex

        os.mkdir(name, mode=0o700, dir_fd=lock.root_fd)
        operation = root / name

        directory_fd = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=lock.root_fd,
        )

        try:
            original = os.fstat(directory_fd)
            current = os.stat(
                name,
                dir_fd=lock.root_fd,
                follow_symlinks=False,
            )

            if (
                not stat.S_ISDIR(original.st_mode)
                or (original.st_dev, original.st_ino)
                != (current.st_dev, current.st_ino)
                or original.st_dev != identity.destination_signature[0]
                or os.listdir(directory_fd)
            ):
                raise StorageUnavailableError(
                    "New backup operation directory is unsafe."
                )

            check_root()

            plan = prepare_real_backup_plan(
                str(root),
                str(operation),
                mount_point,
                volume_uuid,
                device_id,
            )

            check_destination_identity(plan.operation_identity)
            check_root()

            _write_planning_record(directory_fd)

            check_destination_identity(plan.operation_identity)
            check_root()

            yield PreparedRealOperation(operation, plan, lock=lock)

        finally:
            os.close(directory_fd)
