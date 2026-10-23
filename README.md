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

The Python CLI supports dependency checks, destination setup, backup dry runs, and controlled mock execution. Real device backup execution remains disabled.

Run locally:

    PYTHONPATH=src python3 -m iphone_backup_cli --help

The native photo helper is experimental and should only be used in a controlled test environment.

## Safety

The project is designed to keep its backups separate from Finder backups and never automatically delete photos from connected devices.

The backup CLI requires `--dry-run`; real iPhone backup execution remains disabled. The legacy developer preflight simulation launches only a Python no-op. The `simulate` command runs a fixed Python mock writer in a fresh isolated operation directory; neither transfers device data.

The guarded development simulation verifies the volume UUID and directory identity, rejects redirected paths, and opens the operation lock relative to a verified directory descriptor. Health checks run before process launch and during monitoring. These checks do not establish safe behavior for a future real backup engine after a physical SSD disconnect; that still requires controlled validation before enabling real backups.

Full restore compatibility and complete backup integrity verification have not yet been established.

## License

Licensed under GNU GPL v3. See [LICENSE](LICENSE).

## Controlled execution milestone

Use an existing, dedicated disposable directory on a confirmed writable external
volume. The simulation discovers its volume UUID without communicating with any
iPhone. It writes about 5 KB of mock data plus a journal, using a directory
handle inherited by the child. It never invokes `idevicebackup2`, uses a shared
device backup target, overwrites existing output, or promotes a simulation to a
backup. Failed output and journals remain available for inspection.

    PYTHONPATH=src python3 -m iphone_backup_cli simulate --destination /Volumes/DATA/my-disposable-simulations
    PYTHONPATH=src python3 -m iphone_backup_cli simulate --destination /Volumes/DATA/my-disposable-simulations --scenario failure
    PYTHONPATH=src python3 -m iphone_backup_cli simulate --destination /Volumes/DATA/my-disposable-simulations --scenario timeout
    PYTHONPATH=src python3 -m iphone_backup_cli simulation-status /absolute/path/to/.iphone-backup-simulation-<id>

`simulation-status` reads recorded history; it does not revalidate a backup or
resume a transfer. A missing terminal event means incomplete. A malformed or
torn journal fails closed. No command deletes failed output or clears recovery
markers. Review the process state and preserved operation before any manual
recovery. Do not edit a failure journal into a success journal.

| Exit code | Meaning |
| --- | --- |
| 0 | Mock output verified and terminal event recorded, or ordinary CLI success |
| 2 | Invalid command arguments |
| 3 | Real backup execution disabled |
| 4 | Lock unavailable, changed, or quarantined |
| 5 | Storage unavailable/unsafe or journal I/O failure |
| 6 | Mock process or output verification failed |
| 7 | Mock process deadline exceeded |
| 8 | Incomplete recorded simulation |
| 9 | Process cleanup unconfirmed; manual inspection required |
| 130 / 143 | Interrupted with SIGINT / SIGTERM |

The existing backup dry-run/setup/doctor commands retain their general failure
code 1. Low-level process errors also retain reason and process return code.

The original volume and directory identity is retained through execution, and
the advisory lock's inode is checked during monitoring. Fresh operation names
and exclusive descriptor-relative file creation protect existing output. The
supervisor starts a separate process group, handles SIGINT/SIGTERM across launch,
and uses bounded TERM then KILL cleanup, including lingering group descendants.
If cleanup cannot be confirmed, a persistent root marker blocks new operations
when it can be saved. It is never automatically cleared.

### Remaining safety boundaries

- Filesystem checks are observations, not an atomic transaction across mount
  checks, directory creation and child startup. A hostile same-user process can
  race directory creation/open or replace advisory-lock entries. Random operation
  names, pinned handles and exclusive creates reduce exposure; they do not prove
  absolute containment. ExFAT also does not enforce POSIX access permissions.
- A health check may spend up to 15 seconds in `diskutil`; the polling interval
  is not a maximum disconnect response time. Filesystem calls themselves can
  block. An unplug can still lose data, journal updates or filesystem metadata.
- Processes that start another session can escape the original process group;
  uninterruptible kernel I/O may outlive shutdown deadlines. SIGKILL or host
  failure prevents normal journaling and may leave an incomplete operation.
  Unconfirmed quarantine persistence is explicitly reported, never assumed.
- The fixed mock writer is descriptor-aware. A future pathname-based backup
  engine needs a separately validated containment strategy before activation.
  No physical-unplug or real-device acceptance test has been performed here.
- Configuration publishing uses an atomic hard-link operation where supported.
  ExFAT uses exclusive creation with no overwrite; interruption can leave an
  incomplete configuration that must be inspected manually. Readers reject
  invalid JSON rather than silently accepting default settings.

### Verification and release gates

Run the full test suite with disposable fixtures on the external source volume:

    mkdir -p .test-tmp
    TMPDIR="$PWD/.test-tmp" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests

Tests cover success, failed/terminated children, repeated interruptions,
escalation, descriptor inheritance, descendants, lock contention/replacement,
mount/path redirection, malformed volume metadata, existing-output preservation,
journal failures and cleanup quarantine. Device and volume responses in unit
fixtures are simulated; live SSD smoke checks use only newly created disposable
simulation directories. No existing backup directory is needed for validation.

Before the first verified encrypted backup: finish and review real-engine
containment and interrupted-run recovery, then obtain fresh explicit permission
for a controlled device transfer. Confirm encryption, inspect completed backup
metadata and verify backup integrity/restore compatibility. Mock success does
not establish any of those facts. Real transfers remain disabled in this build.

Before v1.0: validate supported macOS/Python/device combinations, incremental
backup behavior, recovery/diagnostics, photo archiving and verification,
duplicate handling and retention, plus packaging and restore acceptance. These
planned features are not completed by this execution milestone.
