# iPhone Backup CLI — Decision Register

**Reviewed:** 26 October 2026
**Status:** Active project decision register
**Project:** Independent from GAIN

## Purpose

Preserve our approved decisions and identify unresolved
questions without inventing product requirements.

We make new product decisions when development reaches
the relevant feature, one decision at a time.

## Decision classifications

APPROVED: The founder previously selected this direction.

PLANNED: Part of the intended product scope, but not
necessarily implemented.

CURRENT: A restriction or design of today's prototype.

OPEN: Requires a future decision.

## Approved product decisions

IB-001 — Independent project
Status: APPROVED
iPhone Backup CLI remains independent from GAIN.
Possible future integration requires a founder decision.

IB-002 — Open-source licensing
Status: APPROVED
The project uses GNU GPLv3.

IB-003 — Platform and interface
Status: APPROVED
The first product is a macOS command-line application.

IB-004 — User-controlled storage
Status: APPROVED
Users select dedicated device-backup destinations
and optional separate photo/video destinations.

IB-005 — Existing backup protection
Status: APPROVED
Existing Finder backups and unrelated personal files
must not be silently overwritten or modified.

IB-006 — Photo deletion
Status: APPROVED
The software must not automatically delete photos
or videos from connected devices.

IB-007 — Truthful verification
Status: APPROVED
A completed process does not automatically mean
that a backup is verified or restorable.

IB-008 — Explicit consent
Status: APPROVED
Significant or potentially destructive operations
require explicit user authorization.

IB-009 — Preserve failures
Status: APPROVED
Failed, incomplete, and interrupted operations
must not be recorded as verified successes.

## Planned product capabilities

IB-010 — Distribution
Status: PLANNED
Homebrew and pipx installation.

IB-011 — Device support
Status: PLANNED
Multiple iPhone and iPad devices.

IB-012 — Backup methods
Status: PLANNED
Full and incremental backups where supported.

IB-013 — Encryption
Status: PLANNED
Encryption support; final v1.0 policy remains open.

IB-014 — Unified operation
Status: PLANNED
One user workflow for configured device backup
and optional media archiving, with separate results.

IB-015 — Media archive
Status: PLANNED
Per-device asset tracking, duplicate detection,
verification, and configurable organization.

IB-016 — History and diagnostics
Status: PLANNED
Persistent operation records and diagnostic reporting.

IB-017 — Retention
Status: PLANNED
Manual snapshot retention without automatic
deletion of existing backups.

IB-018 — Destination migration
Status: PLANNED
Allow users to choose whether existing data
should move or remain at its original location.

IB-019 — Device restoration
Status: PLANNED
v1.0 provides restoration guidance,
not automated device restoration.

IB-020 — Software updates
Status: PLANNED
Optional update notifications without silent installation.

## Current engineering restrictions

ENG-001 — Real transfer disabled
Status: CURRENT
The application cannot yet execute real backups
through its public CLI.

ENG-002 — Encrypted backup preflight
Status: CURRENT
The guarded prototype currently requires
backup encryption to be enabled.

ENG-003 — External volume protection
Status: CURRENT
Operations check storage identity, directory
identity, and backup-target availability.

ENG-004 — Process supervision
Status: CURRENT
Guarded execution uses locking, sandboxing,
process monitoring, and failure journaling.

ENG-005 — Native launch
Status: CURRENT
A descriptor-anchored native launcher helps
protect the intended working directory.

ENG-006 — USB permission
Status: CURRENT
The real-backup sandbox plan permits access
to the specific local usbmuxd socket.

ENG-007 — Recovery limits
Status: CURRENT
Physical SSD disconnection and actual backup
restoration have not yet been validated.

ENG-008 — Experimental media helper
Status: CURRENT
The Swift helper is not a complete
production media-archiving implementation.

## Open decisions

OPEN-001 — Final encryption requirements and
secure password-handling experience.

OPEN-002 — Detailed first-run setup and
dependency-repair interaction.

OPEN-003 — Progress display and remaining-time estimates.

OPEN-004 — Final operation report format.

OPEN-005 — Snapshot naming and retention interface.

OPEN-006 — Whether scheduled or automatically
triggered operations should be supported.

OPEN-007 — Detailed media organization controls.

OPEN-008 — Destination migration user experience.

OPEN-009 — Detailed restoration guidance.

OPEN-010 — Public packaging and update delivery details.

OPEN-011 — Whether the successfully developed
software will eventually join GAIN.

## How future decisions are recorded

For each new decision, record:

- Decision ID and date.
- The specific problem.
- Options considered.
- Founder-approved choice.
- Reason and consequences.
- Any earlier decision it replaces.

Do not silently approve open questions.

## Current priority

Complete the documentation foundation,
then return to Step 176 USB verification.

Real backup transfers remain disabled.
