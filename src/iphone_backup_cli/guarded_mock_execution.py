"""Sandboxed mock execution using the real operation allocator.

No code path in this module invokes idevicebackup2.
"""

import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from .backup_process import BackupProcessError, run_monitored_command
from .backup_sandbox import prepare_sandboxed_command
from .real_operation import create_guarded_real_operation
from .storage import StorageUnavailableError, verify_storage
from .storage_identity import check_destination_identity


_WORKER = """
import sys
import time
from pathlib import Path

Path("mock-launch.bin").write_bytes(b"guarded mock only\\n")

if sys.argv[1] == "failure":
    sys.exit(7)

if sys.argv[1] == "timeout":
    time.sleep(60)
"""


@dataclass(frozen=True)
class GuardedMockResult:
    status: str
    exit_code: int
    operation: Path


def _write_mock_result(prepared, status, exit_code):
    identity = prepared.plan.operation_identity

    fd = os.open(
        prepared.path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )

    try:
        info = os.fstat(fd)

        if (
            not stat.S_ISDIR(info.st_mode)
            or (info.st_dev, info.st_ino)
            != identity.destination_signature
        ):
            raise StorageUnavailableError(
                "Operation directory changed before journaling."
            )

        record = {
            "schema": 1,
            "kind": "guarded_mock_execution",
            "status": status,
            "exit_code": exit_code,
            "transfer_started": False,
            "backup_verified": False,
        }

        encoded = (json.dumps(record, sort_keys=True) + "\n").encode()

        output = os.open(
            "mock-result.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )

        try:
            while encoded:
                count = os.write(output, encoded)
                if count <= 0:
                    raise OSError("Mock journal write made no progress.")
                encoded = encoded[count:]
            os.fsync(output)
        finally:
            os.close(output)

        os.fsync(fd)
    finally:
        os.close(fd)


def run_guarded_mock_execution(
    backup_root,
    mount_point,
    volume_uuid,
    device_id,
    *,
    scenario="success",
):
    """Test the guarded launch lifecycle with a harmless Python writer."""

    if scenario not in ("success", "failure", "timeout"):
        raise ValueError("Invalid mock execution scenario.")

    with create_guarded_real_operation(
        backup_root,
        mount_point,
        volume_uuid,
        device_id,
    ) as prepared:

        def check_health():
            verify_storage(backup_root, mount_point, volume_uuid)
            check_destination_identity(prepared.plan.root_identity)
            check_destination_identity(prepared.plan.operation_identity)
            prepared.lock.check()

        command, cwd = prepare_sandboxed_command(
            [sys.executable, "-I", "-c", _WORKER, scenario],
            prepared.path,
        )

        if cwd != prepared.plan.cwd:
            raise ValueError("Mock working directory mismatch.")

        check_health()

        try:
            run_monitored_command(
                command,
                cwd=cwd,
                health_check=check_health,
                check_interval=0.05,
                timeout=0.25 if scenario == "timeout" else 10,
            )
        except BackupProcessError as error:
            if error.cleanup_failed:
                raise

            if error.reason == "timeout":
                status, exit_code = "mock_timed_out", 7
            else:
                status, exit_code = "mock_failed", 6
        else:
            check_health()

            directory_fd = os.open(
                prepared.path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            try:
                info = os.fstat(directory_fd)
                if (info.st_dev, info.st_ino) != prepared.plan.operation_identity.destination_signature:
                    raise StorageUnavailableError("Mock operation directory changed.")

                output_fd = os.open(
                    "mock-launch.bin",
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
                try:
                    if os.read(output_fd, 100) != b"guarded mock only\n":
                        raise ValueError("Mock payload verification failed.")
                finally:
                    os.close(output_fd)
            finally:
                os.close(directory_fd)

            status, exit_code = "mock_succeeded", 0

        check_health()
        _write_mock_result(prepared, status, exit_code)

        return GuardedMockResult(
            status=status,
            exit_code=exit_code,
            operation=prepared.path,
        )
