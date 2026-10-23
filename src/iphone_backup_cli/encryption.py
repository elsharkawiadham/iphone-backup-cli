import subprocess


class EncryptionCheckError(Exception):
    """Backup encryption is disabled or cannot be confirmed."""


def verify_backup_encryption(device_id):
    if (
        not isinstance(device_id, str)
        or not device_id.strip()
        or device_id.startswith("-")
    ):
        raise EncryptionCheckError("Invalid device identifier.")

    try:
        result = subprocess.run(
            [
                "ideviceinfo",
                "-u", device_id,
                "-q", "com.apple.mobile.backup",
                "-k", "WillEncrypt",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        raise EncryptionCheckError(
            "Could not verify device backup encryption."
        ) from error

    value = result.stdout.strip().lower()

    if value == "true":
        return True

    if value == "false":
        raise EncryptionCheckError(
            "Backup encryption is disabled on this device."
        )

    raise EncryptionCheckError(
        "Device did not report a confirmed encryption state."
    )
