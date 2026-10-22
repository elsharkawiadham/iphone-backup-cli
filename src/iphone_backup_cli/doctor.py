import platform
import shutil

from .devices import list_connected_devices


def run_doctor():
    print("\niPhone Backup CLI — Diagnostics")
    print("--------------------------------")

    if platform.system() != "Darwin":
        print("[ERROR] macOS is required")
        return 1

    print("[OK] macOS detected")

    tools = {
        "Homebrew": "brew",
        "Device detection": "idevice_id",
        "Device information": "ideviceinfo",
        "Backup engine": "idevicebackup2",
    }

    missing = []

    for name, command in tools.items():
        path = shutil.which(command)

        if path:
            print(f"[OK] {name}: {path}")
        else:
            print(f"[MISSING] {name}: {command}")
            missing.append(command)

    print("--------------------------------")

    if missing:
        print("RESULT: Missing dependencies")
        return 1

    print("[CHECK] Searching for connected devices...")

    try:
        devices = list_connected_devices()

        if devices:
            print(f"[OK] Connected devices: {len(devices)}")

            for device in devices:
                print(f"     Device: ...{device[-6:]}")
        else:
            print("[INFO] No connected devices detected")

    except Exception as error:
        print(f"[ERROR] Device discovery failed: {type(error).__name__}")
        print("RESULT: Diagnostics incomplete")
        return 1

    print("RESULT: All required CLI tools found")
    return 0
