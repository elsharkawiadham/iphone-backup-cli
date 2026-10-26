# iPhone Backup CLI — Product Brief

**Status:** Independent open-source project, pre-release.
**Reviewed:** 26 October 2026.

## Vision

Build a reusable macOS command-line application that helps people protect their iPhone and iPad data through device backups and optional independent photo/video archives.

The application should make setup, repeated operations, verification, history, recovery from failures, and storage management understandable and safe.

## Company relationship

iPhone Backup CLI is independent from GAIN.

The founder may decide to bring the successfully developed product into GAIN in the future. No integration or ownership change is approved today.

## Target product

- Open-source software under GNU GPLv3.
- macOS command-line interface.
- Planned installation through Homebrew and pipx.
- User-selected local storage destinations.
- Support for multiple iPhones and iPads.
- Full and incremental backups where supported.
- Encryption support, with final product policy unresolved.
- Optional separate photo and video archiving.
- Duplicate detection and appropriate file verification.
- Persistent operation history and diagnostics.
- Safe handling of interrupted operations.
- Manual snapshot retention.
- Destination changes and verified data migration.
- Restore guidance, without automated restoration in v1.0.
- Optional update notifications without automatic installation.

## Intended user journey

1. Discover and install the application.
2. Run Doctor to check the Mac, dependencies, and device connection.
3. Complete guided setup and select dedicated storage locations.
4. Connect the iPhone or iPad and the configured storage device.
5. Select a device where necessary.
6. Launch the configured backup and optional media archive workflows.
7. Perform preflight checks before transferring data.
8. Create the supported device backup.
9. Independently archive eligible new photos and videos when enabled.
10. Verify supported results and report verification limitations.
11. Record backup and media outcomes separately.
12. Return later for subsequent operations and history inspection.
13. Manage retained backups and storage destinations safely.
14. Use documented recovery guidance when restoration is needed.

The planned combined operation command is `iphone-backup run`.
The planned history and verification commands are `iphone-backup history` and `iphone-backup verify`.

These commands are product goals, not currently implemented commands.

## Non-negotiable safety principles

- Preserve existing Finder backups and unrelated personal files.
- Never silently overwrite an existing backup target.
- Never automatically delete photos or videos from the iPhone.
- Never silently write to a different storage volume.
- Never claim a backup is verified solely because a process exited successfully.
- Keep device backups and photo archives independently identifiable.
- Preserve failed or interrupted operation evidence.
- Require explicit consent for significant or destructive actions.
- Do not include personal backup contents or credentials in public source files.

## Current implementation boundary

The project already has a CLI foundation, setup and diagnostics, backup dry runs, guarded mock execution, process monitoring, filesystem safety checks, a native launcher, and experimental media access.

Real guarded iPhone backup transfers remain disabled.

The production media archive, full verification workflow, history interface, destination migration, and public release are not complete.

## Decisions deliberately postponed

- Exact first-run screens and prompts.
- Final encrypted-backup and password-handling experience.
- Progress indicators and time estimates.
- Report appearance and snapshot naming.
- Automatic schedules or connection-triggered runs.
- Detailed storage migration and reorganization interaction.
- Exact restore-guidance experience.
- Public installation and update details.

These questions will be resolved one at a time when development reaches them.

## Release principle

Public v1.0 requires implemented features, tested failure handling, truthful integrity reporting, supported-platform validation, and practical restore-compatibility evidence.

Successful simulations alone do not establish backup reliability.
