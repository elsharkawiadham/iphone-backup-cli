import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_backup_cli.backup_lock import acquire_backup_lock
from iphone_backup_cli.backup_process import BackupProcessError
from iphone_backup_cli.controlled_execution import (
    ExitCode, read_simulation_status, run_controlled_simulation,
)
from iphone_backup_cli.execution_preflight import prepare_backup_execution
from iphone_backup_cli.storage import StorageUnavailableError


class ControlledExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mount = Path(self.temp.name).resolve()
        self.root = self.mount / 'dedicated-simulations'
        self.root.mkdir()
        for target in ('iphone_backup_cli.storage_identity.os.path.ismount',):
            p = patch(target, return_value=True)
            p.start()
            self.addCleanup(p.stop)
        storage_patcher = patch('iphone_backup_cli.controlled_execution.verify_storage')
        self.storage = storage_patcher.start()
        self.addCleanup(storage_patcher.stop)

    def run_mock(self, **kwargs):
        return run_controlled_simulation(str(self.root), str(self.mount), 'mock-volume', **kwargs)

    def test_real_child_writes_verified_payload_and_success_journal(self):
        with patch('iphone_backup_cli.controlled_execution.run_monitored_command', wraps=__import__(
            'iphone_backup_cli.backup_process', fromlist=['run_monitored_command']).run_monitored_command) as runner:
            result = self.run_mock()
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.status, 'simulation_succeeded')
        self.assertTrue(result.journal_recorded)
        self.assertEqual(read_simulation_status(result.operation), result)
        command = runner.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertNotIn('idevicebackup2', command)
        self.assertTrue(runner.call_args.kwargs['pass_fds'])
        self.assertEqual(set(p.name for p in self.root.iterdir() if not p.name.startswith('._')),
                         {result.operation.name, '.iphone-backup-cli.lock'})

    def test_failed_child_preserves_output_and_is_never_success(self):
        result = self.run_mock(scenario='failure')
        self.assertEqual(result.exit_code, ExitCode.PROCESS_FAILED)
        self.assertEqual(result.process_returncode, 7)
        self.assertEqual(read_simulation_status(result.operation).status, 'process_failed')
        self.assertTrue((result.operation / 'mock-payload.bin').exists())
        with acquire_backup_lock(self.root):
            pass

    def test_timeout_is_distinct_and_preserves_artifacts(self):
        result = self.run_mock(scenario='timeout')
        self.assertEqual(result.exit_code, ExitCode.TIMED_OUT)
        self.assertEqual(read_simulation_status(result.operation).status, 'timed_out')

    def test_existing_personal_and_device_files_are_unchanged(self):
        existing = self.root / ('a' * 40)
        existing.mkdir()
        personal = existing / 'Manifest.db'
        personal.write_bytes(b'existing backup sentinel')
        result = self.run_mock()
        again = self.run_mock()
        self.assertEqual(result.exit_code, 0)
        self.assertNotEqual(result.operation, again.operation)
        self.assertEqual(personal.read_bytes(), b'existing backup sentinel')

    def test_root_replaced_after_lock_never_writes_fallback(self):
        original_mkdir = os.mkdir
        previous = self.mount / 'original'
        def replace(path, mode=0o777, *, dir_fd=None):
            if dir_fd is not None:
                self.root.rename(previous)
                self.root.mkdir()
            return original_mkdir(path, mode, dir_fd=dir_fd)
        with patch('iphone_backup_cli.controlled_execution.os.mkdir', side_effect=replace):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.LOCKED)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertFalse(any(p.name == 'mock-payload.bin' for p in previous.rglob('*')))

    def test_storage_loss_during_run_retains_incomplete_journal(self):
        def failed(command, **kwargs):
            self.storage.side_effect = StorageUnavailableError('simulated disconnect')
            kwargs['health_check']()
        with patch('iphone_backup_cli.controlled_execution.run_monitored_command', side_effect=failed):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.STORAGE_UNAVAILABLE)
        self.assertFalse(result.journal_recorded)
        self.assertEqual(read_simulation_status(result.operation).exit_code, ExitCode.INCOMPLETE)

    def test_interrupt_is_journaled_after_cleanup(self):
        with patch('iphone_backup_cli.controlled_execution.run_monitored_command', side_effect=KeyboardInterrupt):
            result = self.run_mock()
        self.assertEqual(result.exit_code, 130)
        self.assertEqual(read_simulation_status(result.operation).status, 'interrupted')

    def test_initial_storage_failure_creates_nothing(self):
        self.storage.side_effect = StorageUnavailableError('gone')
        result = self.run_mock()
        self.assertIsNone(result.operation)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_lock_contention_creates_no_operation(self):
        with acquire_backup_lock(self.root):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.LOCKED)
        self.assertFalse(any(p.is_dir() for p in self.root.iterdir()))

    def test_invalid_scenario_prevents_writes(self):
        with self.assertRaises(ValueError):
            self.run_mock(scenario='idevicebackup2')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_child_output_collision_never_overwrites(self):
        def collide(command, **kwargs):
            fd = kwargs['pass_fds'][0]
            out = os.open('mock-payload.bin', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
            os.write(out, b'sentinel')
            os.close(out)
            from iphone_backup_cli.backup_process import run_monitored_command
            return run_monitored_command(command, **kwargs)
        with patch('iphone_backup_cli.controlled_execution.run_monitored_command', side_effect=collide):
            with contextlib.redirect_stderr(io.StringIO()):
                result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.PROCESS_FAILED)
        self.assertEqual((result.operation / 'mock-payload.bin').read_bytes(), b'sentinel')

    def test_malformed_journal_fails_closed(self):
        result = self.run_mock()
        (result.operation / 'event-2.json').write_text('[]')
        with self.assertRaises(ValueError):
            read_simulation_status(result.operation)

    def test_status_rejects_journal_symlink(self):
        result = self.run_mock()
        event = result.operation / 'event-2.json'
        target = result.operation / 'saved.json'
        event.rename(target)
        event.symlink_to(target)
        with self.assertRaises(OSError):
            read_simulation_status(result.operation)

    def test_terminal_journal_io_failure_never_reports_success(self):
        original_open = os.open
        def fail(path, *args, **kwargs):
            if path == 'event-2.json':
                raise OSError('simulated full disk')
            return original_open(path, *args, **kwargs)
        with patch('iphone_backup_cli.controlled_execution.os.open', side_effect=fail):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.STORAGE_UNAVAILABLE)
        self.assertFalse(result.journal_recorded)
        self.assertEqual(read_simulation_status(result.operation).status, 'incomplete')

    def test_cleanup_uncertainty_quarantines_root_until_manual_inspection(self):
        error = BackupProcessError('Mock group still visible', reason='timeout', cleanup_failed=True)
        with patch('iphone_backup_cli.controlled_execution.run_monitored_command', side_effect=error):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.CLEANUP_UNCONFIRMED)
        self.assertEqual(read_simulation_status(result.operation).status, 'cleanup_unconfirmed')
        again = self.run_mock()
        self.assertEqual(again.exit_code, ExitCode.LOCKED)
        self.assertIsNone(again.operation)

    def test_interrupt_during_quarantine_preserves_cleanup_uncertainty(self):
        error = BackupProcessError('Mock group still visible', cleanup_failed=True)
        with patch('iphone_backup_cli.controlled_execution.run_monitored_command', side_effect=error), patch(
            'iphone_backup_cli.backup_lock.BackupLockGuard.quarantine', side_effect=KeyboardInterrupt
        ):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.CLEANUP_UNCONFIRMED)
        self.assertFalse(result.journal_recorded)
        self.assertEqual(read_simulation_status(result.operation).status, 'incomplete')

    def test_operation_directory_sync_failure_never_reports_success(self):
        import stat
        original_sync = os.fsync
        def fail(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('simulated directory sync failure')
            return original_sync(fd)
        with patch('iphone_backup_cli.controlled_execution.os.fsync', side_effect=fail):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.STORAGE_UNAVAILABLE)
        self.assertFalse(result.journal_recorded)
        self.assertIsNotNone(result.operation)

    def test_missing_output_never_passes_verification(self):
        with patch('iphone_backup_cli.controlled_execution.run_monitored_command', return_value=0):
            result = self.run_mock()
        self.assertEqual(result.exit_code, ExitCode.PROCESS_FAILED)
        self.assertEqual(result.status, 'verification_failed')

    def test_corrupted_status_cannot_report_shell_success(self):
        result = self.run_mock(scenario='failure')
        event = result.operation / 'event-2.json'
        data = json.loads(event.read_text())
        for replacement in ({'exit_code': 0}, {'status': []}, {'detail': []}, {'process_returncode': True}):
            with self.subTest(replacement=replacement):
                event.write_text(json.dumps({**data, **replacement}))
                with self.assertRaises(ValueError):
                    read_simulation_status(result.operation)

    def test_exclusive_operation_collision_preserves_existing_content(self):
        first = self.run_mock()
        before = (first.operation / 'mock-payload.bin').read_bytes()
        class SameID:
            hex = first.operation.name.rsplit('-', 1)[-1]
        with patch('iphone_backup_cli.controlled_execution.uuid.uuid4', return_value=SameID()):
            collision = self.run_mock()
        self.assertNotEqual(collision.exit_code, 0)
        self.assertEqual((first.operation / 'mock-payload.bin').read_bytes(), before)

    def test_original_preflight_identity_is_not_recaptured(self):
        device = 'a' * 40
        previous = self.mount / 'previous'
        @contextlib.contextmanager
        def replaced(*args, **kwargs):
            with prepare_backup_execution(*args, **kwargs) as prepared:
                self.root.rename(previous)
                self.root.mkdir()
                yield prepared
        with patch('iphone_backup_cli.execution_preflight.verify_storage'), patch(
            'iphone_backup_cli.execution_preflight.verify_backup_encryption'
        ), patch('iphone_backup_cli.backup_execution.verify_storage'), patch(
            'iphone_backup_cli.backup_execution.prepare_backup_execution', side_effect=replaced
        ), patch('iphone_backup_cli.backup_execution.run_monitored_command') as runner:
            from iphone_backup_cli.backup_execution import simulate_backup_execution
            with self.assertRaises(StorageUnavailableError):
                simulate_backup_execution(str(self.root), str(self.mount), 'uuid', device)
        runner.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])


class SimulationCLITests(unittest.TestCase):
    def test_real_backup_disabled_before_any_device_access(self):
        from iphone_backup_cli.cli import main
        with patch.object(sys, 'argv', ['iphone-backup', 'backup']), patch(
            'iphone_backup_cli.cli.run_backup_dry_run'
        ) as dry_run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), ExitCode.REAL_BACKUP_DISABLED)
        dry_run.assert_not_called()

    def test_simulation_failure_exit_code_reaches_shell(self):
        from iphone_backup_cli.cli import main
        from iphone_backup_cli.controlled_execution import ExecutionResult
        with patch.object(sys, 'argv', ['iphone-backup', 'simulate', '--destination', '/mock']), patch(
            'iphone_backup_cli.storage.identify_volume', return_value={'mount_point':'/mount','volume_uuid':'uuid'}
        ), patch('iphone_backup_cli.controlled_execution.run_controlled_simulation',
                 return_value=ExecutionResult('process_failed', 6)), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 6)


if __name__ == '__main__':
    unittest.main()
