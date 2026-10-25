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


# Explicit USB-only capability. Keep ordinary simulations on the original
# network-denying profile. The canonical socket path was verified on macOS.
USBMUX_SANDBOX_PROFILE = SANDBOX_PROFILE + """
(allow system-socket (socket-domain AF_UNIX))
(allow network-outbound
    (remote unix-socket
        (path-literal "/private/var/run/usbmuxd")))
"""


def prepare_sandboxed_command(
    command, writable_directory, *, allow_usbmux=False
):
    """Return a sandbox command and its anchored working directory."""

    if type(allow_usbmux) is not bool:
        raise BackupSandboxError("USB socket permission must be boolean.")

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
        USBMUX_SANDBOX_PROFILE if allow_usbmux else SANDBOX_PROFILE,
        *command,
    ]

    return launch, resolved
