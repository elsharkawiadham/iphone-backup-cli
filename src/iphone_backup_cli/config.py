import errno
import json
import os
import shutil
import tempfile
from pathlib import Path


APP_DIR = (
    Path.home()
    / "Library"
    / "Application Support"
    / "iPhoneBackupCLI"
)

CONFIG_FILE = APP_DIR / "config.json"


def load_config():
    if not CONFIG_FILE.is_file():
        return None

    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def _publish_exclusively(temp_path):
    """Preserve no-clobber publication on filesystems without hardlinks.

    This fallback has no atomic visibility guarantee: readers may encounter
    incomplete JSON and must fail closed. On failure retain the destination
    for deliberate recovery; never unlink a pathname another writer may have
    replaced. The exclusive open cannot overwrite an existing file or symlink.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(CONFIG_FILE, flags, 0o600)
    with os.fdopen(fd, "wb") as destination:
        with open(temp_path, "rb") as source:
            shutil.copyfileobj(source, destination)
        destination.flush()
        os.fsync(destination.fileno())


def save_config(config):
    """Save once without replacing an existing configuration.

    Hardlink-capable filesystems publish an already flushed file atomically.
    ExFAT uses exclusive creation instead; interrupted copies remain blocking
    and are never silently replaced on a subsequent setup attempt. POSIX file
    modes are requested but cannot be enforced by filesystems such as ExFAT.
    """
    APP_DIR.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".config-",
        suffix=".tmp",
        dir=APP_DIR,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            os.chmod(temp_path, 0o600)
            json.dump(config, file, indent=2)
            file.flush()
            os.fsync(file.fileno())

        try:
            os.link(temp_path, CONFIG_FILE)
        except OSError as error:
            if error.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS):
                raise
            _publish_exclusively(temp_path)

    finally:
        Path(temp_path).unlink(missing_ok=True)
