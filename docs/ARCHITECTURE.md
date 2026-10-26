# iPhone Backup CLI — System Architecture

**Reviewed:** 26 October 2026
**Status:** Experimental architecture
**Project:** Independent from GAIN

## 1. System overview

iPhone Backup CLI is a macOS command-line application
for iPhone/iPad backups and optional media archiving.

The architecture separates:
- User commands and configuration.
- Device discovery and verification.
- Backup planning and execution.
- External storage protection.
- Process monitoring and recovery.
- Photo/video import.
- Operation history and verification.

Only some of these components are implemented today.

## 2. Technology stack

- Python: application CLI and orchestration.
- libimobiledevice: iPhone/iPad communication and backups.
- idevicebackup2: underlying backup engine.
- C: descriptor-anchored native launcher.
- macOS sandbox-exec: subprocess isolation.
- Swift/ImageCaptureCore: experimental photo/video access.
- Local files: configuration and operation records.
- Git and automated unittest suite: development and verification.

There is no required integration with GAIN.

## 3. Command-line interface

Main entry point:
src/iphone_backup_cli/cli.py

Existing commands:
- doctor
- setup
- backup --dry-run
- simulate
- simulation-status

Future planned commands:
- run
- verify
- history

Real backup execution is currently disabled.

## 4. Configuration and device discovery

doctor.py checks basic system dependencies and device discovery.

setup.py validates backup and optional photo destinations.

config.py manages saved application configuration.

devices.py communicates with libimobiledevice to discover devices.

encryption.py checks device backup encryption status.

## 5. Storage protection

storage.py identifies and verifies external storage volumes.

storage_identity.py records and checks filesystem identities.

backup_target.py protects existing backup targets.

backup_lock.py prevents conflicting participating operations
and handles cleanup quarantine.

execution_preflight.py combines checks required before
a guarded backup operation.

The application must not silently overwrite existing
Finder backups or redirect transfers to another volume.

## 6. Backup planning

backup.py provides the existing backup dry run.

backup_command.py constructs backup-engine commands.

real_backup_plan.py prepares a sandboxed command
without executing a real backup.

guarded_real_plan.py and real_operation.py manage
guarded planning, operation allocation, and initial records.

Planning a backup is not the same as executing or
verifying a backup.

## 7. Process execution and containment

backup_process.py supervises subprocesses,
interruptions, timeouts, and cleanup.

backup_sandbox.py restricts filesystem writes
and provides a narrow optional USB socket permission.

anchored_launch.py prepares a descriptor-anchored launch.

native/AnchoredLauncher.c enters an already-open
directory before executing the child process.

The USB-specific sandbox permits communication through
/private/var/run/usbmuxd.

Ordinary simulation processes do not need this permission.

Successful USB discovery does not prove full backup
protocol compatibility.

## 8. Simulation architecture

backup_execution.py provides an older safe execution
simulation path.

controlled_execution.py provides mock execution,
event recording, and status inspection.

guarded_mock_execution.py tests the newer
guarded-operation architecture with a mock child process.

Mock execution never establishes that an actual
iPhone backup is complete or recoverable.

## 9. Backup operation records

Current operation artifacts may include:

- planning.json: an operation was prepared.
- mock-result.json: guarded mock outcome.
- event-*.json: simulation history events.
- .iphone-backup-cli.lock: exclusive operation guard.
- .iphone-backup-cli.cleanup-unconfirmed:
  manual-inspection barrier after uncertain cleanup.

Incomplete records must not be promoted to success.

## 10. Photo and video architecture

native/PhotoHelper.swift experiments with
ImageCaptureCore media detection and file copying.

Its Info.plist describes the native application's identity
and media-access purpose.

The production media archive still requires:
- A per-device asset database.
- Duplicate detection.
- Verified import and retry handling.
- Configurable organization.
- Independent media operation reporting.

Automatic deletion from the iPhone is not approved.

## 11. Important safety boundaries

Filesystem identity checks cannot make every
filesystem operation atomic.

ExFAT lacks some POSIX filesystem protections.

Physical SSD disconnection may cause lost or incomplete
writes despite process monitoring.

Process cleanup cannot guarantee that every possible
child process terminates immediately.

Real backup password handling is not complete.

Successful process exit does not establish backup
integrity or restoration compatibility.

The native launcher still needs release-grade
building and verification.

## 12. Planned architectural development

Future components will support:
- Real guarded backup execution.
- Independent backup integrity verification.
- Persistent user-facing history.
- Full photo/video import and deduplication.
- Safe storage migrations.
- Backup retention management.
- Restore guidance.
- Public installation and update delivery.

Each component requires implementation and testing
before it can be described as operational.

## 13. Related project documents

PRODUCT_BRIEF.md defines the product.

ROADMAP.md tracks development milestones.

DECISIONS.md records approved and unresolved decisions.

TEST_PLAN.md defines verification and release requirements.
