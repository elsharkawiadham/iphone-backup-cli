import json
import os
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


def save_config(config):
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

        os.link(temp_path, CONFIG_FILE)

    finally:
        Path(temp_path).unlink(missing_ok=True)
