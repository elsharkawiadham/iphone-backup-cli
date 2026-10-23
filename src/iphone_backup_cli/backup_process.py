import subprocess


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


def run_monitored_command(command, timeout=None):
    """Run a command with exit-code and interruption handling."""
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
        or timeout <= 0
    ):
        raise ValueError("Invalid process timeout.")

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
        )
    except OSError as error:
        raise BackupProcessError(
            "Could not start the backup process."
        ) from error

    try:
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _stop_process(process)
        raise BackupProcessError(
            "Backup process timed out."
        ) from error
    except KeyboardInterrupt:
        _stop_process(process)
        raise

    if exit_code != 0:
        raise BackupProcessError(
            f"Backup process exited with code {exit_code}."
        )

    return exit_code
