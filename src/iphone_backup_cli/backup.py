import json
import subprocess

from .config import load_config
from .backup_command import build_backup_command
from .backup_target import BackupTargetError, check_new_backup_target
from .encryption import EncryptionCheckError, verify_backup_encryption
from .devices import list_connected_devices
from .storage import StorageUnavailableError, verify_storage


def run_backup_dry_run(device_id=None):
    print("\niPhone Backup CLI — Backup Dry Run")
    print("----------------------------------")

    try:
        settings = load_config()

        if not isinstance(settings, dict):
            raise ValueError("Run setup before backing up.")

        destination = settings["backup_destination"]
        volume = settings["backup_volume"]

        if not isinstance(destination, str) or not isinstance(volume, dict):
            raise ValueError("Invalid backup configuration.")

        mount_point = volume["mount_point"]
        volume_uuid = volume["volume_uuid"]

        if not all(
            isinstance(value, str) and value
            for value in (destination, mount_point, volume_uuid)
        ):
            raise ValueError("Incomplete storage configuration.")

        verify_storage(destination, mount_point, volume_uuid)

        print("[OK] External storage identity verified")
        print(f"[OK] Backup destination: {destination}")

        devices = list_connected_devices()

        if not devices:
            print("[ERROR] No connected iPhone or iPad detected")
            return 1

        if device_id is None:
            if len(devices) != 1:
                print("[ERROR] Multiple devices connected")
                print("Specify a device using --device.")
                return 1
            device_id = devices[0]

        if device_id not in devices:
            print("[ERROR] Selected device is not connected")
            return 1

        print(f"[OK] Selected device: ...{device_id[-6:]}")
        verify_backup_encryption(device_id)
        print("[OK] Encrypted backups enabled")

        check_new_backup_target(destination, device_id)
        print("[OK] New device backup target is available")

        command = build_backup_command(device_id, destination)

        print("[OK] Backup command prepared")
        print(f"[OK] Command arguments: {len(command)}")
        print("[SAFE] Backup execution is disabled")

        print("\nDRY RUN PASSED")
        print("No backup was started.")
        return 0

    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        json.JSONDecodeError,
        StorageUnavailableError,
        EncryptionCheckError,
        BackupTargetError,
        subprocess.SubprocessError,
    ) as error:
        print(f"[ERROR] Preflight failed: {error}")
        print("No backup was started.")
        return 1
