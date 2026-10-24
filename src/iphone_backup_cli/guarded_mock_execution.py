"""Sandboxed mock execution using the real operation allocator.

No code path in this module invokes idevicebackup2.
"""

import json
import os
import signal
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .anchored_launch import prepare_anchored_launch
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



@contextmanager
def _launch_configuration(command, cwd, prepared, native_launcher):
    """Keep the operation descriptor open during anchored execution."""

    if native_launcher is None:
        yield command, {"cwd": cwd}
        return

    with prepare_anchored_launch(
        command,
        prepared.path,
        prepared.plan.operation_identity,
        native_launcher,
    ) as (anchored_command, inherited_fds):
        yield anchored_command, {"pass_fds": inherited_fds}


def run_guarded_mock_execution(
    backup_root,
    mount_point,
    volume_uuid,
    device_id,
    *,
    scenario="success",
    native_launcher=None,
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
            with _launch_configuration(
                command, cwd, prepared, native_launcher
            ) as (launch_command, launch_options):
                run_monitored_command(
                    launch_command,
                    health_check=check_health,
                    check_interval=0.05,
                    timeout=0.25 if scenario == "timeout" else 10,
                    **launch_options,
                )
        except BaseException as error:
            if getattr(error, "cleanup_failed", False):
                # Cleanup uncertainty takes priority over every other status.
                # A persistent marker prevents future operations from starting
                # until the surviving-process risk is inspected manually.
                prepared.lock.quarantine(prepared.path.name)
                status, exit_code = "mock_cleanup_unconfirmed", 9

            elif isinstance(error, KeyboardInterrupt):
                status, exit_code = "mock_interrupted", 130

            elif isinstance(error, BackupProcessError):
                if error.reason == "timeout":
                    status, exit_code = "mock_timed_out", 7
                elif error.reason == "interrupted":
                    status = "mock_interrupted"
                    exit_code = (
                        143 if error.signal_number == signal.SIGTERM else 130
                    )
                else:
                    status, exit_code = "mock_failed", 6

            else:
                raise
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
