import math
import subprocess
import time


class BackupProcessError(Exception):
    """A managed backup process failed."""


def _stop_process(process):
    """Request a clean shutdown, then force-stop if necessary."""
    if process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_monitored_command(
    command,
    timeout=None,
    health_check=None,
    check_interval=1.0,
):
    """Run a command with interruption and optional health monitoring."""
    if (
        not isinstance(command, (list, tuple))
        or not command
        or not all(
            isinstance(argument, str) and argument
            for argument in command
        )
    ):
        raise ValueError("Invalid process command.")

    if timeout is not None and (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("Invalid process timeout.")

    if health_check is not None and not callable(health_check):
        raise ValueError("Health check must be callable.")

    if (
        isinstance(check_interval, bool)
        or not isinstance(check_interval, (int, float))
        or not math.isfinite(check_interval)
        or check_interval <= 0
    ):
        raise ValueError("Invalid health check interval.")

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
        )
    except OSError as error:
        raise BackupProcessError(
            "Could not start the backup process."
        ) from error

    started = time.monotonic()

    try:
        while True:
            if health_check is not None:
                health_check()

            if timeout is None:
                wait_time = (
                    check_interval if health_check is not None else None
                )
            else:
                remaining = timeout - (time.monotonic() - started)

                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)

                wait_time = (
                    min(check_interval, remaining)
                    if health_check is not None
                    else remaining
                )

            try:
                exit_code = process.wait(timeout=wait_time)
                break
            except subprocess.TimeoutExpired:
                if (
                    timeout is not None
                    and time.monotonic() - started >= timeout
                ):
                    raise

    except subprocess.TimeoutExpired as error:
        _stop_process(process)
        raise BackupProcessError(
            "Backup process timed out."
        ) from error
    except BaseException:
        _stop_process(process)
        raise

    if exit_code != 0:
        raise BackupProcessError(
            f"Backup process exited with code {exit_code}."
        )

    if health_check is not None:
        health_check()

    return exit_code
