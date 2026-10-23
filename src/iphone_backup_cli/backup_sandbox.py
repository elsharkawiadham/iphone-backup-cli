"""macOS sandbox launcher preparation. Does not execute backups."""

from pathlib import Path


class BackupSandboxError(Exception):
    """A sandboxed process cannot be prepared safely."""


SANDBOX_PROFILE = """
(version 1)
(deny default)
(allow process*)
(allow file-read*)
(allow mach-lookup)
(allow sysctl-read)
(allow file-write* (literal "/dev/null"))
(allow file-write* (subpath (param "WRITABLE_ROOT")))
"""


def prepare_sandboxed_command(command, writable_directory):
    """Return a sandbox command and its anchored working directory."""

    if (
        not isinstance(command, (list, tuple))
        or not command
        or not all(isinstance(arg, str) and arg for arg in command)
    ):
        raise BackupSandboxError("Invalid command.")

    executable = Path(command[0])

    if not executable.is_absolute() or not executable.is_file():
        raise BackupSandboxError("Executable must be an absolute file path.")

    root = Path(writable_directory).expanduser()

    if not root.is_absolute() or root.is_symlink():
        raise BackupSandboxError("Invalid writable directory.")

    try:
        resolved = root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise BackupSandboxError("Writable directory unavailable.") from error

    if not resolved.is_dir():
        raise BackupSandboxError("Writable destination is not a directory.")

    sandbox = Path("/usr/bin/sandbox-exec")

    if not sandbox.is_file():
        raise BackupSandboxError("macOS sandbox-exec is unavailable.")

    launch = [
        str(sandbox),
        "-D",
        f"WRITABLE_ROOT={resolved}",
        "-p",
        SANDBOX_PROFILE,
        *command,
    ]

    return launch, resolved
