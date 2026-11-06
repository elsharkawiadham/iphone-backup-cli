import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from iphone_backup_cli.prelaunch_orchestration import (
    prepare_checked_launch_intent,
)


class TestPrelaunchOrchestration(unittest.TestCase):

    def setUp(self):
        self.root = Path("/mock-volume/Backups")
        self.operation = self.root / (
            ".iphone-backup-operation-" + "0" * 32
        )
        self.device = "a" * 40
        self.command = (
            "/usr/bin/sandbox-exec",
            "-p",
            "mock-profile",
            "/opt/homebrew/bin/idevicebackup2",
            "backup",
            ".",
        )

        self.plan = SimpleNamespace(
            command=self.command,
            cwd=self.operation,
            target=self.operation / self.device,
            root_identity=object(),
            operation_identity=object(),
        )

        self.prepared = SimpleNamespace(
            path=self.operation,
            plan=self.plan,
            state="planned_only",
            lock=object(),
        )

        patcher = patch(
            "iphone_backup_cli.prelaunch_orchestration."
            "require_fresh_prelaunch_safety",
            return_value=True,
        )
        self.gate = patcher.start()
        self.addCleanup(patcher.stop)

    def check(self):
        return prepare_checked_launch_intent(
            self.prepared,
            str(self.root),
            "/mock-volume",
            "mock-uuid",
            self.device,
        )

    def test_success_preserves_original_plan(self):
        result = self.check()
        self.assertEqual(result.command, self.command)
        self.assertEqual(result.cwd, self.operation)
        self.gate.assert_called_once()

    def test_security_exception_prevents_handoff(self):
        self.gate.side_effect = RuntimeError("Safety check failed")
        with self.assertRaisesRegex(RuntimeError, "Safety check failed"):
            self.check()

    def test_false_security_result_prevents_handoff(self):
        self.gate.return_value = False
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            self.check()

    def test_unexpected_operation_state_rejected(self):
        self.prepared.state = "running"
        with self.assertRaises(ValueError):
            self.check()
        self.gate.assert_not_called()

    def test_empty_command_rejected(self):
        self.plan.command = ()
        with self.assertRaises(ValueError):
            self.check()
        self.gate.assert_not_called()

    def test_non_tuple_command_rejected(self):
        self.plan.command = list(self.command)
        with self.assertRaises(ValueError):
            self.check()
        self.gate.assert_not_called()

    def test_wrong_working_directory_rejected(self):
        self.plan.cwd = self.root
        with self.assertRaises(ValueError):
            self.check()
        self.gate.assert_not_called()

    def test_wrong_backup_root_rejected(self):
        self.prepared.path = Path("/different-volume/operation")
        with self.assertRaises(ValueError):
            self.check()
        self.gate.assert_not_called()

    def test_command_changed_during_verification(self):
        def mutate(*args):
            self.plan.command = ("changed",)
            return True

        self.gate.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            self.check()

    def test_target_changed_during_verification(self):
        def mutate(*args):
            self.plan.target = self.operation / ("b" * 40)
            return True

        self.gate.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            self.check()

    def test_directory_changed_during_verification(self):
        def mutate(*args):
            self.prepared.path = self.root
            return True

        self.gate.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            self.check()

    def test_lock_changed_during_verification(self):
        def mutate(*args):
            self.prepared.lock = object()
            return True

        self.gate.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            self.check()

    def test_identity_changed_during_verification(self):
        def mutate(*args):
            self.plan.operation_identity = object()
            return True

        self.gate.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            self.check()

    def test_plan_replaced_during_verification(self):
        def mutate(*args):
            self.prepared.plan = object()
            return True

        self.gate.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            self.check()


if __name__ == "__main__":
    unittest.main()
