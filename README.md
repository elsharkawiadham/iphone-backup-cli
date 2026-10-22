# iPhone Backup CLI

An open-source macOS command-line project for backing up iPhones and iPads and archiving photos and videos.

## Project status

Early development — version 0.1.0.

This software is experimental and is not ready to serve as someone's only device backup.

## Current progress

- Python CLI foundation
- Encrypted iPhone backup feasibility tested with libimobiledevice
- Encrypted backup manifest successfully inspected and verified
- Native Swift helper using Apple's ImageCaptureCore
- Programmatic iPhone media detection and file copying demonstrated
- Configurable destination argument for experimental media transfers

## Planned v1.0 features

- Guided setup and user-selected backup destinations
- Multi-device support
- Incremental backups where supported
- Optional encrypted backups
- Photo and video archiving
- Duplicate detection and file verification
- Backup history and diagnostics
- Safe recovery from interrupted operations
- Manual snapshot retention

## Requirements

- macOS 14 or newer (planned support)
- Python 3.11–3.14 (compatibility testing pending)
- Homebrew and libimobiledevice for the backup engine
- Swift compiler for the experimental native helper

## Development

The Python CLI currently supports help and version information.

Run locally:

    PYTHONPATH=src python3 -m iphone_backup_cli --help

The native photo helper is experimental and should only be used in a controlled test environment.

## Safety

The project is designed to keep its backups separate from Finder backups and never automatically delete photos from connected devices.

Full restore compatibility and complete backup integrity verification have not yet been established.

## License

Licensed under GNU GPL v3. See [LICENSE](LICENSE).
