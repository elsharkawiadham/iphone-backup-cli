"""Directory replacement tests for guarded, descriptor-anchored mocks."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import BackupLockError
from iphone_backup_cli.backup_process import run_monitored_command
from iphone_backup_cli.guarded_mock_execution import (
    run_guarded_mock_execution,
)
from iphone_backup_cli.storage import StorageUnavailableError


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "native"
    / "AnchoredLauncher.c"
)


@unittest.skipUnless(sys.platform == "darwin", "macOS only")
class TestAnchoredFailureInjection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)

        cls.launcher = Path(temporary.name) / "launcher"

        subprocess.run(
            [
                "xcrun", "clang", str(SOURCE),
                "-Wall", "-Wextra", "-Werror",
                "-o", str(cls.launcher),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=45,
        )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.mount = Path(temporary.name).resolve()
        self.root = self.mount / "Backups"
        self.root.mkdir()

        self.args = (
            str(self.root),
            str(self.mount),
            "test-volume",
            "a" * 40,
        )

        targets = (
            "iphone_backup_cli.execution_preflight.verify_storage",
            "iphone_backup_cli.execution_preflight.verify_backup_encryption",
            "iphone_backup_cli.real_backup_plan.verify_storage",
            "iphone_backup_cli.real_operation.verify_storage",
            "iphone_backup_cli.guarded_mock_execution.verify_storage",
        )

        for target in targets:
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

        mount_patcher = patch(
            "iphone_backup_cli.storage_identity.os.path.ismount",
            return_value=True,
        )
        mount_patcher.start()
        self.addCleanup(mount_patcher.stop)

        binary_patcher = patch(
            "iphone_backup_cli.real_backup_plan.IDEVICEBACKUP2",
            Path(sys.executable),
        )
        binary_patcher.start()
        self.addCleanup(binary_patcher.stop)

    def operation(self):
        operations = list(
            self.root.glob(".iphone-backup-operation-*")
        )
        self.assertEqual(len(operations), 1)
        return operations[0]

    def inject_failure(self, mutation, *, after_launch=False):
        observed = {"health_checks": 0, "mutation": False}

        def intercept(command, **options):
            if not after_launch:
                mutation()
                observed["mutation"] = True
            else:
                original_health = options["health_check"]

                def injected_health():
                    observed["health_checks"] += 1

                    # The supervisor's first check precedes Popen.
                    # Its second check happens after Popen returns.
                    if observed["health_checks"] == 2:
                        mutation()
                        observed["mutation"] = True

                    original_health()

                options["health_check"] = injected_health

            return run_monitored_command(command, **options)

        with patch(
            "iphone_backup_cli.guarded_mock_execution.run_monitored_command",
            side_effect=intercept,
        ):
            with self.assertRaises(
                (StorageUnavailableError, BackupLockError)
            ) as raised:
                run_guarded_mock_execution(
                    *self.args,
                    scenario="timeout" if after_launch else "success",
                    native_launcher=self.launcher,
                )

        self.assertTrue(observed["mutation"])

        if after_launch:
            self.assertGreaterEqual(
                observed["health_checks"], 2
            )

        self.assertFalse(
            getattr(raised.exception, "cleanup_failed", False),
            "Process cleanup was not confirmed.",
        )

    def test_operation_replaced_before_launch(self):
        preserved = self.root / "preserved-operation"

        def mutate():
            operation = self.operation()
            operation.rename(preserved)
            operation.mkdir()

        self.inject_failure(mutate)

        self.assertTrue(
            (preserved / "planning.json").exists()
        )
        self.assertFalse(
            (preserved / "mock-result.json").exists()
        )

        replacement = self.operation()
        self.assertEqual(list(replacement.iterdir()), [])

    def test_operation_replaced_after_launch(self):
        preserved = self.root / "preserved-operation"

        def mutate():
            operation = self.operation()
            operation.rename(preserved)
            operation.mkdir()

        self.inject_failure(mutate, after_launch=True)

        self.assertTrue(
            (preserved / "planning.json").exists()
        )
        self.assertFalse(
            (preserved / "mock-result.json").exists()
        )

        replacement = self.operation()
        self.assertEqual(list(replacement.iterdir()), [])

    def test_backup_root_replaced_after_launch(self):
        preserved_root = self.mount / "preserved-root"

        def mutate():
            self.root.rename(preserved_root)
            self.root.mkdir()

        self.inject_failure(mutate, after_launch=True)

        self.assertEqual(list(self.root.iterdir()), [])

        preserved_operations = list(
            preserved_root.glob(".iphone-backup-operation-*")
        )

        self.assertEqual(len(preserved_operations), 1)
        self.assertTrue(
            (preserved_operations[0] / "planning.json").exists()
        )
        self.assertFalse(
            (preserved_operations[0] / "mock-result.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
