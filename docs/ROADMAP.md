# iPhone Backup CLI — Development Roadmap

**Reviewed:** 26 October 2026
**Project status:** Experimental, pre-release
**Version:** 0.1.0
**Ownership:** Independent from GAIN

## Development principles

- Protect existing data before introducing new functionality.
- Develop one verified milestone at a time.
- Separate automated tests from physical-device verification.
- Never claim a backup is restorable without supporting evidence.
- Resolve product-design decisions when development reaches them.
- Do not enable real backup transfers without explicit approval.
- Do not integrate the project into GAIN without a future founder decision.

## M0 — Project foundation

Status: IMPLEMENTED IN INITIAL FORM

Completed:
- Public GitHub repository and GPLv3 licensing.
- Python package and command-line foundation.
- Initial Doctor diagnostics.
- Guided destination setup.
- Device detection and encryption checks.
- Backup dry-run command.
- Experimental Swift photo/media helper.

Remaining:
- Public installer verification.
- Supported macOS and Python compatibility testing.
- Complete first-run user experience.

## M1 — Backup safety infrastructure

Status: IMPLEMENTED AND TESTED IN SIMULATIONS

Completed:
- External volume identity verification.
- Existing backup target protection.
- Exclusive operation locking.
- Guarded operation directories.
- Sandboxed mock execution.
- Native descriptor-anchored launcher.
- Process supervision and signal handling.
- Timeout and failure handling.
- Operation journaling.
- Cleanup quarantine.
- Directory replacement and interruption tests.

Important:
Passing simulated tests does not establish safety during
a physical SSD disconnect or actual device backup.

## M2 — Restricted USB and real-engine preparation

Status: IN PROGRESS

Completed:
- idevicebackup2 1.4.0 runtime startup verified.
- Direct USB device discovery verified.
- Restricted sandbox USB socket requirement identified.
- Specific usbmuxd socket permission implemented.
- Negative network restriction tests passed.
- Non-interactive backup command planning implemented.

Pending:
- Confirm native launcher plus restricted USB discovery.
- Verify real backup-protocol compatibility.
- Finalize secure backup-password handling.
- Validate production native launcher build and identity.
- Review live-transfer interruption and recovery safety.

Checkpoint:
318 automated tests passed on 11 November 2026 (default TMPDIR).
The output of Step 176's integrated USB verification
has not yet been provided.

## M3 — First controlled encrypted backup

Status: NOT STARTED THROUGH THE GUARDED REAL WORKFLOW

Requirements before execution:
- Complete M2 safety reviews.
- Protect all existing backup archives.
- Select and verify a fresh isolated destination.
- Confirm device identity, storage and encryption.
- Obtain explicit founder approval for the transfer.

Acceptance:
- Backup transfer completes with honest status reporting.
- Existing backups remain untouched.
- Generated metadata is inspected.
- Supported integrity checks are performed.
- Restore compatibility is investigated separately.

A successful process exit alone is insufficient.

## M4 — Complete device-backup workflow

Status: PLANNED

- Full and incremental backups where supported.
- Multiple-device selection.
- Repeated backup workflows.
- Persistent backup history.
- Verification and diagnostics commands.
- Manual snapshot retention.
- Safe interruption and failure recovery.
- User-facing restore guidance.

## M5 — Photo and video archiving

Status: EXPERIMENTAL FOUNDATION

Completed:
- Experimental ImageCaptureCore media detection.
- Single-file media copying and hash verification experiment.

Pending:
- Production media import workflow.
- Per-device asset tracking database.
- Duplicate detection.
- Verified source and destination comparisons.
- Configurable media organization.
- Independent media operation history.
- Safe retries after partial imports.

Automatic deletion from the iPhone is not approved.

## M6 — Storage management

Status: PLANNED

- Change configured storage destinations.
- Choose whether to move or leave existing archives.
- Verify migrated data.
- Preserve originals until migration completion.
- Safely reorganize photo archives.
- Handle interrupted migrations.

## M7 — Public v1.0 release

Status: NOT READY

Requirements:
- Planned v1.0 features implemented and tested.
- Homebrew and pipx distribution validated.
- macOS and Python compatibility confirmed.
- Real-device backup reliability assessed.
- Practical restore compatibility evaluated.
- Photo archiving and verification tested.
- Documentation and CLI behavior aligned.
- Security and privacy review completed.
- Known limitations published.

## Current development priority

1. Establish authoritative project documentation.
2. Resume Step 176 native USB discovery verification.
3. Address real-engine compatibility and password security.
4. Review the first controlled backup safety gates.
5. Request explicit approval before any real transfer.

## Development checkpoint

The latest supplied local Git inventory shows main
six commits ahead of origin/main.

The documentation changes are not yet committed.

Actual physical backup and restore verification
remain outstanding.

## Related documents

- PRODUCT_BRIEF.md — product requirements and user journey.
- ARCHITECTURE.md — technical components and safety boundaries.
- DECISIONS.md — approved and unresolved choices.
- TEST_PLAN.md — tests and acceptance criteria.
