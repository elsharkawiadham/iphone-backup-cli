"""Descriptor-anchored mock execution. No real backup engine is enabled here."""
import json
import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from .backup_lock import BackupLockError, acquire_backup_lock
from .backup_process import BackupProcessError, run_monitored_command
from .backup_sandbox import prepare_sandboxed_command
from .storage import StorageUnavailableError, verify_storage
from .storage_identity import capture_destination_identity, check_destination_identity


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID = 2
    REAL_BACKUP_DISABLED = 3
    LOCKED = 4
    STORAGE_UNAVAILABLE = 5
    PROCESS_FAILED = 6
    TIMED_OUT = 7
    INCOMPLETE = 8
    CLEANUP_UNCONFIRMED = 9
    INTERRUPTED = 130
    TERMINATED = 143


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    exit_code: int
    operation: Path | None = None
    detail: str = ""
    journal_recorded: bool = False
    process_returncode: int | None = None


_PAYLOAD = b"iphone-backup-cli disposable simulation\n" * 128
# The child receives an inherited directory descriptor, never an absolute
# output pathname or arbitrary command. It cannot initiate a device transfer.
_WORKER = """
import os, sys, time
fd = int(sys.argv[1])
scenario = sys.argv[2]
try:
    out = os.open('mock-payload.bin', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
except FileExistsError:
    sys.exit(17)
try:
    data = b'iphone-backup-cli disposable simulation\\n' * 128
    while data:
        data = data[os.write(out, data):]
    os.fsync(out)
finally:
    os.close(out)
if scenario == 'failure':
    sys.exit(7)
if scenario == 'timeout':
    time.sleep(60)
"""
_TERMINAL = {
    "simulation_succeeded", "process_failed", "timed_out", "interrupted",
    "storage_unavailable", "lock_lost", "verification_failed", "cleanup_unconfirmed",
}


def _signature(fd):
    value = os.fstat(fd)
    return value.st_dev, value.st_ino


def _open_directory(path, *, dir_fd=None):
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)


class _Operation:
    def __init__(self, root, lock, identity, health_check):
        self.lock = lock
        self.identity = identity
        self.health_check = health_check
        self.name = '.iphone-backup-simulation-' + uuid.uuid4().hex
        self.path = Path(root) / self.name
        self.fd = None
        self.sequence = 0
        self.created = False

    def create(self):
        self.health_check()
        os.mkdir(self.name, mode=0o700, dir_fd=self.lock.root_fd)
        self.created = True
        os.fsync(self.lock.root_fd)
        try:
            self.fd = _open_directory(self.name, dir_fd=self.lock.root_fd)
            self.signature = _signature(self.fd)
            if self.signature[0] != self.identity.destination_signature[0] or os.listdir(self.fd):
                raise StorageUnavailableError('Operation directory is unsafe.')
            self.check()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def check(self):
        self.lock.check()
        check_destination_identity(self.identity)
        current = os.stat(self.name, dir_fd=self.lock.root_fd, follow_symlinks=False)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != self.signature:
            raise StorageUnavailableError('Operation directory identity changed.')
        if _signature(self.fd) != self.signature:
            raise StorageUnavailableError('Operation descriptor identity changed.')

    def record(self, status, **fields):
        self.health_check()
        self.check()
        event = {'schema': 1, 'kind': 'simulation', 'sequence': self.sequence,
                 'operation': self.name, 'status': status, **fields}
        encoded = (json.dumps(event, sort_keys=True) + '\n').encode()
        fd = os.open(f'event-{self.sequence}.json',
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=self.fd)
        try:
            while encoded:
                written = os.write(fd, encoded)
                if written <= 0:
                    raise OSError('Journal write made no progress.')
                encoded = encoded[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        self.sequence += 1

    def verify_payload(self):
        self.check()
        try:
            fd = os.open('mock-payload.bin', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError as error:
            raise ValueError('Simulation output is missing.') from error
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != len(_PAYLOAD):
                raise ValueError('Simulation output verification failed.')
            if os.read(fd, len(_PAYLOAD) + 1) != _PAYLOAD:
                raise ValueError('Simulation output verification failed.')
        finally:
            os.close(fd)


def run_controlled_simulation(destination, mount_point, volume_uuid, *, scenario='success', sandboxed=False):
    """Run a fixed mock writer in a new directory. Never overwrite/resume/promote."""
    if type(sandboxed) is not bool:
        raise ValueError('Sandbox option must be a boolean.')
    if scenario not in {'success', 'failure', 'timeout'}:
        raise ValueError('Unknown simulation scenario.')
    operation = None
    status = 'storage_unavailable'
    code = ExitCode.STORAGE_UNAVAILABLE
    detail = ''
    returncode = None
    recorded = False
    try:
        identity = capture_destination_identity(destination, mount_point)
        verify_storage(destination, mount_point, volume_uuid)
        check_destination_identity(identity)
        with acquire_backup_lock(destination, expected_signature=identity.destination_signature) as lock:
            def check():
                verify_storage(destination, mount_point, volume_uuid)
                check_destination_identity(identity)
                lock.check()
                if operation is not None and operation.fd is not None:
                    operation.check()

            operation = _Operation(destination, lock, identity, check)
            try:
                # Assign ownership before creation so partial allocation is
                # still reported and its descriptor always closes on failure.
                operation.create()
                operation.record('created')
                operation.record('running')
                try:
                    worker_command = [
                        sys.executable, '-I', '-c', _WORKER,
                        str(operation.fd), scenario,
                    ]
                    if sandboxed:
                        worker_command, _ = prepare_sandboxed_command(
                            worker_command, operation.path
                        )
                    run_monitored_command(
                        worker_command,
                        pass_fds=(operation.fd,), timeout=0.25 if scenario == 'timeout' else 10,
                        check_interval=0.05, health_check=check,
                    )
                    operation.verify_payload()
                    status, code = 'simulation_succeeded', ExitCode.SUCCESS
                except BaseException as error:
                    if getattr(error, 'cleanup_failed', False):
                        status, code = 'cleanup_unconfirmed', ExitCode.CLEANUP_UNCONFIRMED
                        detail = str(error) + ' Process cleanup could not be confirmed. Inspect manually.'
                        try:
                            lock.quarantine(operation.name)
                        except (BackupLockError, OSError) as quarantine_error:
                            detail += ' Quarantine could not be persisted: ' + str(quarantine_error)
                    elif isinstance(error, BackupProcessError):
                        returncode = error.returncode
                        reason = error.reason
                        if reason == 'interrupted':
                            status = 'interrupted'
                            code = ExitCode.TERMINATED if error.signal_number == 15 else ExitCode.INTERRUPTED
                        elif reason == 'timeout':
                            status, code = 'timed_out', ExitCode.TIMED_OUT
                        else:
                            status, code = 'process_failed', ExitCode.PROCESS_FAILED
                        detail = str(error)
                    elif isinstance(error, KeyboardInterrupt):
                        status, code, detail = 'interrupted', ExitCode.INTERRUPTED, 'Simulation interrupted.'
                    elif isinstance(error, ValueError):
                        status, code, detail = 'verification_failed', ExitCode.PROCESS_FAILED, str(error)
                    else:
                        raise
                operation.record(status, exit_code=int(code), detail=detail, process_returncode=returncode)
                recorded = True
            finally:
                operation.close()
    except BackupLockError as error:
        if code != ExitCode.CLEANUP_UNCONFIRMED:
            status, code, detail = 'lock_lost', ExitCode.LOCKED, str(error)
    except (StorageUnavailableError, OSError) as error:
        if code != ExitCode.CLEANUP_UNCONFIRMED:
            status, code, detail = 'storage_unavailable', ExitCode.STORAGE_UNAVAILABLE, str(error)
    except KeyboardInterrupt:
        if code != ExitCode.CLEANUP_UNCONFIRMED:
            status, code, detail = 'interrupted', ExitCode.INTERRUPTED, 'Simulation interrupted.'
        else:
            detail += ' Quarantine or terminal journaling was interrupted; persistence is unconfirmed.'
    return ExecutionResult(status, int(code), operation.path if operation and operation.created else None, detail, recorded, returncode)


def read_simulation_status(operation_path):
    """Read owned event files without writing, resuming, or trusting success alone."""
    path = Path(operation_path).expanduser()
    if not path.is_absolute() or '..' in path.parts or path.resolve(strict=True) != path:
        raise ValueError('Operation path must be absolute and canonical.')
    if re.fullmatch(r'\.iphone-backup-simulation-[0-9a-f]{32}', path.name) is None:
        raise ValueError('Not a simulation operation directory.')
    directory = _open_directory(path)
    try:
        events = []
        names = os.listdir(directory)
        indices = sorted(int(name[6:-5]) for name in names if re.fullmatch(r'event-[0-9]+\.json', name))
        if indices != list(range(len(indices))) or len(indices) > 3:
            raise ValueError('Invalid simulation journal sequence.')
        for index in indices:
            fd = os.open(f'event-{index}.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
                    raise ValueError('Invalid simulation journal file.')
                event = json.loads(os.read(fd, 65537))
            finally:
                os.close(fd)
            if not isinstance(event, dict) or event.get('schema') != 1 or event.get('kind') != 'simulation' or event.get('operation') != path.name or event.get('sequence') != index:
                raise ValueError('Invalid simulation journal event.')
            events.append(event)
        expected = ['created', 'running']
        if any(event.get('status') != expected[index] for index, event in enumerate(events[:2])):
            raise ValueError('Invalid simulation journal transitions.')
        if len(events) < 3:
            return ExecutionResult('incomplete', int(ExitCode.INCOMPLETE), path,
                                   'No terminal event; preserved for inspection. No automatic resume.')
        final = events[-1]
        valid_codes = {
            'simulation_succeeded': {0}, 'process_failed': {6}, 'timed_out': {7},
            'interrupted': {130, 143}, 'storage_unavailable': {5}, 'lock_lost': {4},
            'verification_failed': {6}, 'cleanup_unconfirmed': {9},
        }
        status = final.get('status')
        returncode = final.get('process_returncode')
        if (not isinstance(status, str) or status not in _TERMINAL
                or type(final.get('exit_code')) is not int
                or final['exit_code'] not in valid_codes[status]
                or not isinstance(final.get('detail', ''), str)
                or (returncode is not None and type(returncode) is not int)):
            raise ValueError('Invalid terminal simulation event.')
        # This reports recorded simulation history, never backup integrity.
        return ExecutionResult(final['status'], final['exit_code'], path, final.get('detail', ''), True,
                               final.get('process_returncode'))
    finally:
        os.close(directory)
