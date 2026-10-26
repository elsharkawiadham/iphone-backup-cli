# iPhone Backup CLI — Test and Acceptance Plan

**Reviewed:** 26 October 2026
**Status:** Active development test plan
**Project:** Independent from GAIN

## 1. Testing principles

- Protect existing Finder backups and personal data.
- Use isolated directories and synthetic data whenever possible.
- Keep simulated tests separate from physical-device verification.
- Never treat a successful process exit as proof of recoverability.
- Never publish credentials or private device information.
- Require explicit approval before any real backup transfer.
- Preserve incomplete and failed operation records.

## 2. Automated regression tests

Run from the repository root:

PYTHONPATH=src python3 -m unittest discover -s tests -q

Latest founder-reported result:
256 tests passed on 26 October 2026.

The latest actual test execution is always authoritative.

## 3. Existing automated test coverage

- CLI behavior and diagnostics.
- Configuration setup and persistence.
- Device discovery.
- Backup encryption checks.
- External volume identity validation.
- Existing backup target protection.
- Backup planning.
- Operation locking and quarantine.
- Process monitoring and timeouts.
- SIGINT and SIGTERM interruption handling.
- Native descriptor-anchored launching.
- Sandbox filesystem restrictions.
- Directory replacement and failure injection.
- Mock execution success and failure journals.
- Restricted USB socket access.
- Blocking unrelated TCP and Unix socket connections.

Many tests use simulated devices and storage conditions.

## 4. Read-only physical-device testing

Verify:
- Connected device discovery outside the sandbox.
- Device discovery inside the restricted sandbox.
- Device discovery through the native launcher.
- Correct backup-engine version and command support.
- No unexpected network permissions.
- No modification of device data or backup archives.

The Step 176 integrated USB verification result
is still awaiting confirmation.

## 5. First real backup prerequisites

Before enabling a real backup:

- Complete restricted USB communication checks.
- Investigate actual backup-protocol compatibility.
- Finalize safe encryption/password handling.
- Verify the intended destination and volume UUID.
- Verify the selected device and encryption requirements.
- Protect all existing Finder and experimental backups.
- Confirm available space and exclusive operation access.
- Validate native launcher build and executable identity.
- Review failure containment and recovery records.
- Obtain explicit founder permission for the transfer.

Real backup execution remains disabled today.

## 6. Real backup acceptance

A successful test must establish:

- A new isolated backup was created.
- No existing personal backup was overwritten.
- The correct device and destination were used.
- The actual transfer outcome was recorded.
- Backup metadata was inspected.
- Supported integrity checks were completed.
- Unverified properties were disclosed clearly.

Restore compatibility requires separate testing.

## 7. Interruption and failure acceptance

Test:
- User cancellation.
- Device communication failure.
- Backup engine failure.
- Process timeout.
- Storage becoming unavailable.
- Partial or malformed operation records.
- Lock conflicts.
- Unconfirmed process cleanup.
- Safe behavior on the next launch.

Do not report success when cleanup or completion
cannot be confirmed.

Physical SSD unplug testing must never use
irreplaceable personal backup data.

## 8. Photo and video archive acceptance

Verify:
- Supported photo/video import.
- Detection of new assets.
- Duplicate handling.
- Per-device asset tracking.
- Source and destination hash checks where possible.
- Honest reporting when source verification is unavailable.
- Configured folder organization.
- Interrupted import and safe retry.
- Independent backup and photo operation results.
- No automatic deletion from the iPhone.

The current Swift helper does not meet
all production archive requirements.

## 9. History and retention acceptance

- Correctly preserve operation outcomes.
- Distinguish verified and unverified backups.
- Preserve older snapshots unless the user
  explicitly approves an applicable deletion.
- Handle incomplete or corrupted history safely.
- Provide reliable read-only diagnostics.

## 10. Destination migration acceptance

- Ask whether to move or leave existing data.
- Verify the new storage destination.
- Avoid overwriting unrelated existing files.
- Verify copied content.
- Preserve original data until migration succeeds.
- Recover safely from incomplete migration.

## 11. Restoration acceptance

v1.0 plans restore guidance, not automated restoration.

Test documented restoration compatibility
before claiming a backup is recoverable.

A successful backup command does not
guarantee successful device restoration.

## 12. Public release requirements

- Approved v1.0 scope implemented.
- Real backup workflow tested.
- Backup integrity and restoration evidence documented.
- Photo archive and duplicate handling tested.
- Failure recovery and retention tested.
- Supported macOS and Python versions verified.
- Homebrew and pipx installation tested.
- Public documentation matches real behavior.
- Security and privacy review completed.
- Known limitations published.

## 13. Evidence for every milestone

Record:
- Relevant Git commit.
- Tests performed.
- Pass/fail results.
- Tested environment where applicable.
- Known limitations.
- Remaining release blockers.

No milestone is complete merely because
it appears in the roadmap.

## Related documents

- PRODUCT_BRIEF.md
- ROADMAP.md
- ARCHITECTURE.md
- DECISIONS.md
