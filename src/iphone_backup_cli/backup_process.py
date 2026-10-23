"""Bounded supervision for a process and its original POSIX process group.

A process that creates a new session escapes this group. Kernel I/O can also
remain uninterruptible. This supervisor therefore provides best-effort cleanup,
not proof that an unplugged volume or every descendant is safe.
"""

import math
import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class BackupProcessError(Exception):
    """A managed command failed, with stable machine-readable metadata."""

    def __init__(self, message, *, reason="failed", returncode=None,
                 cleanup_failed=False):
        super().__init__(message)
        self.reason = reason
        self.returncode = returncode
        self.cleanup_failed = cleanup_failed
        self.signal_number = (
            -returncode if isinstance(returncode, int) and returncode < 0
            else None
        )


class BackupProcessInterruptedError(BackupProcessError):
    """The supervisor received a termination request."""

    def __init__(self, signal_number):
        super().__init__(
            f"Backup process interrupted by signal {signal_number}.",
            reason="interrupted",
            returncode=-signal_number,
        )
        self.signal_number = signal_number


def _positive_seconds(value, label):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError(f"Invalid {label}.")


@contextmanager
def _interruption_requests():
    """Record signals without raising in the Popen ownership handoff window."""
    requested = []
    previous = {}
    if threading.current_thread() is threading.main_thread():
        def request(signum, _frame):
            if not requested:
                requested.append(signum)

        try:
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.signal(signum, request)
            yield requested
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    else:
        # Python only permits signal handlers in the main thread. Callers that
        # require CLI signal supervision must invoke this on the main thread.
        yield requested


def _raise_interruption(requested):
    if requested:
        if requested[0] == signal.SIGINT:
            raise KeyboardInterrupt()
        raise BackupProcessInterruptedError(requested[0])


def _process_group(process):
    pid = process.pid
    return pid if os.name == "posix" and isinstance(pid, int) and pid > 0 else None


def _group_exists(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        # Inability to inspect a group is not evidence that it has stopped.
        return True


def _still_running(process, group):
    leader_running = process.poll() is None
    return _group_exists(group) if group is not None else leader_running


def _signal_process(process, group, signum):
    try:
        if group is not None:
            os.killpg(group, signum)
        elif process.poll() is None:
            if signum == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        return True
    except ProcessLookupError:
        return True  # Exit between poll and signal is expected.
    except OSError:
        # Still try to stop/reap the leader if group signalling failed.
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            pass
        return False


def _wait_stopped(process, group, seconds):
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return not _still_running(process, group)
        try:
            process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired:
            pass
        if not _still_running(process, group):
            return True
        # wait() returns immediately after the leader exits, while its group
        # may still contain children. Avoid spinning during that cleanup.
        if process.poll() is not None:
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))


def _stop_process(process, group=None, stop_timeout=1.0, kill_timeout=1.0):
    """Signal the original group, reap the leader, and bound every wait."""
    if not _still_running(process, group):
        return True
    signalled = _signal_process(process, group, signal.SIGTERM)
    if _wait_stopped(process, group, stop_timeout):
        return signalled
    killed = _signal_process(process, group, signal.SIGKILL)
    stopped = _wait_stopped(process, group, kill_timeout)
    return signalled and killed and stopped


def _emergency_kill(process, group, kill_timeout):
    """Last bounded attempt when normal cleanup cannot poll or wait reliably."""
    try:
        if group is not None:
            os.killpg(group, signal.SIGKILL)
        else:
            process.kill()
    except OSError:
        # Avoid poll() here: it may be the operation that just failed.
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=kill_timeout)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _record_cleanup_failure(error):
    error.cleanup_failed = True
    error.add_note(
        "Could not confirm process-group cleanup within the shutdown deadline."
    )


def run_monitored_command(
    command,
    timeout=None,
    health_check=None,
    check_interval=1.0,
    *,
    pass_fds=(),
    cwd=None,
    stop_timeout=1.0,
    kill_timeout=1.0,
):
    """Run without a shell, supervising health, signals and the original group.

    Pass only explicitly pinned descriptors in ``pass_fds``. Descriptors remain
    owned by the caller. Main-thread callers receive scoped SIGINT/SIGTERM
    handling; handlers are restored on every exit path. Shutdown is bounded,
    and ``cleanup_failed`` marks an inability to confirm the group's exit.
    """
    if (not isinstance(command, (list, tuple)) or not command
            or not all(isinstance(argument, str) and argument
                       and "\0" not in argument for argument in command)):
        raise ValueError("Invalid process command.")
    if timeout is not None:
        _positive_seconds(timeout, "process timeout")
    if health_check is not None and not callable(health_check):
        raise ValueError("Health check must be callable.")
    _positive_seconds(check_interval, "health check interval")
    _positive_seconds(stop_timeout, "process shutdown timeout")
    _positive_seconds(kill_timeout, "process kill timeout")
    if (not isinstance(pass_fds, (tuple, list))
            or any(isinstance(fd, bool) or not isinstance(fd, int) or fd < 0
                   for fd in pass_fds)):
        raise ValueError("Invalid inherited process descriptors.")
    if pass_fds and os.name != "posix":
        raise ValueError("Inherited process descriptors require POSIX.")

    working_directory = None
    if cwd is not None:
        working_directory = Path(cwd).expanduser()
        if not working_directory.is_absolute() or working_directory.is_symlink():
            raise ValueError('Invalid process working directory.')
        try:
            resolved = working_directory.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError('Process working directory unavailable.') from error
        if resolved != working_directory or not resolved.is_dir():
            raise ValueError('Unsafe process working directory.')

    process = None
    group = None
    with _interruption_requests() as requested:
        try:
            if health_check is not None:
                health_check()
            _raise_interruption(requested)
            started = time.monotonic()
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    start_new_session=(os.name == "posix"),
                    pass_fds=tuple(pass_fds),
                    **({'cwd': str(working_directory)}
                       if working_directory is not None else {}),
                )
            except OSError as error:
                _raise_interruption(requested)
                raise BackupProcessError(
                    "Could not start the backup process.", reason="start"
                ) from error
            group = _process_group(process)

            while True:
                _raise_interruption(requested)
                if health_check is not None:
                    health_check()
                wait_time = check_interval
                if timeout is not None:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise BackupProcessError(
                            "Backup process timed out.", reason="timeout"
                        )
                    wait_time = min(wait_time, remaining)
                try:
                    exit_code = process.wait(timeout=wait_time)
                    break
                except subprocess.TimeoutExpired:
                    continue

            _raise_interruption(requested)
            if exit_code != 0:
                raise BackupProcessError(
                    f"Backup process exited with code {exit_code}.",
                    reason="signal" if exit_code < 0 else "exit",
                    returncode=exit_code,
                )
            if health_check is not None:
                health_check()
            _raise_interruption(requested)
            if group is not None and _group_exists(group):
                raise BackupProcessError(
                    "Backup process exited while descendants were still running.",
                    reason="descendants", returncode=exit_code,
                )
            return exit_code
        except BaseException as error:
            if process is not None:
                try:
                    cleaned = _stop_process(process, group, stop_timeout, kill_timeout)
                except OSError:
                    cleaned = False
                if not cleaned:
                    _emergency_kill(process, group, kill_timeout)
                    _record_cleanup_failure(error)
                if (isinstance(error, BackupProcessError)
                        and error.returncode is None):
                    try:
                        error.returncode = process.poll()
                    except OSError:
                        if cleaned:
                            _emergency_kill(process, group, kill_timeout)
                            _record_cleanup_failure(error)
            raise
