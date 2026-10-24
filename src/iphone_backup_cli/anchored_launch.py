"""Prepare a descriptor-anchored process launch. No backup execution."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def prepare_anchored_launch(command, directory, identity, launcher):
    """Keep the original directory open through supervised process startup."""

    executable = Path(launcher).expanduser()
    if (
        not executable.is_absolute()
        or executable.is_symlink()
        or not executable.is_file()
        or not os.access(executable, os.X_OK)
    ):
        raise ValueError("Native launcher unavailable or unsafe.")

    if (
        not isinstance(command, (list, tuple))
        or not command
        or not all(isinstance(arg, str) and arg for arg in command)
    ):
        raise ValueError("Invalid anchored command.")

    path = Path(directory).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("Invalid anchored directory.")

    fd = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )

    try:
        opened = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        signature = (opened.st_dev, opened.st_ino)

        if (
            not stat.S_ISDIR(opened.st_mode)
            or signature != identity.destination_signature
            or signature != (current.st_dev, current.st_ino)
            or not stat.S_ISDIR(current.st_mode)
        ):
            raise ValueError("Anchored directory identity changed.")

        launch = [
            str(executable),
            str(fd),
            *command,
        ]

        yield launch, (fd,)

    finally:
        os.close(fd)
