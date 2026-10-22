import subprocess


def list_connected_devices():
    result = subprocess.run(
        ["idevice_id", "-l"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]
