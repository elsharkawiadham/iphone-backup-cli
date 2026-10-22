import os
from pathlib import Path

from .config import CONFIG_FILE, save_config


def validate_destination(value):
    path = Path(value.strip()).expanduser()

    if not path.is_absolute():
        raise ValueError("Enter an absolute directory path.")

    path = path.resolve(strict=True)

    if not path.is_dir():
        raise ValueError("Destination must be a directory.")

    if path.is_mount() or path == Path.home().resolve():
        raise ValueError(
            "Select a dedicated subdirectory, not a drive or home root."
        )

    if any(path.iterdir()):
        raise ValueError(
            "Destination must be empty for initial setup."
        )

    if "mobilesync_backup" in [
        part.lower() for part in path.parts
    ]:
        raise ValueError(
            "Do not use an existing Finder backup directory."
        )

    if not os.access(path, os.W_OK):
        raise ValueError("Destination is not writable.")

    return str(path)


def run_setup():
    if CONFIG_FILE.exists():
        print("Configuration already exists.")
        print("Existing settings were not changed.")
        return 1

    print("\niPhone Backup CLI — Setup")
    print("-------------------------")
    print("Use dedicated directories for backups and photos.")
    print("Do not select an existing Finder backup directory.\n")

    try:
        backup = validate_destination(
            input("Backup destination: ")
        )

        answer = input(
            "Enable photo/video archiving? [y/N]: "
        ).strip().lower()

        if answer not in ("", "y", "yes", "n", "no"):
            raise ValueError("Please answer yes or no.")

        photo_enabled = answer in ("y", "yes")
        photo_destination = None

        if photo_enabled:
            photo_destination = validate_destination(
                input("Photo archive destination: ")
            )

            if photo_destination == backup:
                raise ValueError(
                    "Backup and photo destinations must differ."
                )

        settings = {
            "backup_destination": backup,
            "photo_archive_enabled": photo_enabled,
            "photo_destination": photo_destination,
        }

        save_config(settings)

    except (ValueError, OSError, EOFError) as error:
        print(f"Setup failed: {error}")
        return 1
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        return 130

    print("\nSUCCESS: Configuration saved.")
    print("No backup or photo transfer has started.")
    return 0
