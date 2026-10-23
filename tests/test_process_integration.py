"""Real Python subprocess fixtures; no device tooling or existing backup paths."""
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from iphone_backup_cli.backup_process import BackupProcessError, run_monitored_command
from iphone_backup_cli.storage import StorageUnavailableError


@unittest.skipUnless(os.name == "posix", "POSIX process-group integration")
class TestProcessIntegration(unittest.TestCase):

    def setUp(self):
        # Keep all fixture writes on the same external SSD as these tests.
        self.temporary = tempfile.TemporaryDirectory(
            prefix=".process-fixture-", dir=Path(__file__).resolve().parent,
        )
        self.directory = Path(self.temporary.name)
        self.lifetime = self.directory / "fixture-alive"
        self.lifetime.write_text("alive")
        self.supervisors = []

    def stop_supervisor(self, process):
        # Only direct, unreaped children are signalled through their Popen
        # handle. Never send a terminating signal to a PID read from a file.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def tearDown(self):
        # Descendants self-expire if a failing supervisor leaves one behind.
        # Removing this private token avoids stale-PID cleanup races entirely.
        self.lifetime.unlink(missing_ok=True)
        try:
            for process in self.supervisors:
                self.stop_supervisor(process)
        finally:
            self.temporary.cleanup()

    def script(self, name, code):
        target = self.directory / name
        source = textwrap.dedent(code)
        source = source.replace(
            "while True:",
            f"while Path({str(self.lifetime)!r}).exists() and time.monotonic() < _fixture_deadline:",
        )
        source = ("import time\nfrom pathlib import Path\n"
                  "_fixture_deadline = time.monotonic() + 10\n" + source)
        target.write_text(source)
        return target

    def command(self, script):
        return [sys.executable, str(script)]

    def read_pid(self, path):
        # Used only for signal-0 assertions; this grants no ownership to kill.
        return int(path.read_text())

    def test_timeout_terminates_leader_and_child(self):
        pidfile = self.directory / "child.pid"
        stopped = self.directory / "child.stopped"
        child = self.script("child.py", f'''
            import os, signal, time
            from pathlib import Path
            def stop(*_args):
                Path({str(stopped)!r}).write_text("stopped")
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop)
            Path({str(pidfile)!r} + ".tmp").write_text(str(os.getpid()))
            os.replace({str(pidfile)!r} + ".tmp", {str(pidfile)!r})
            while True:
                time.sleep(0.01)
        ''')
        leader = self.script("leader.py", f'''
            import signal, subprocess, sys, time
            child = subprocess.Popen([sys.executable, {str(child)!r}])
            def stop(*_args):
                child.wait(timeout=1)
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop)
            while True:
                time.sleep(0.01)
        ''')
        with self.assertRaises(BackupProcessError) as raised:
            run_monitored_command(self.command(leader), timeout=0.5,
                                  check_interval=0.01, stop_timeout=1)
        pid = self.read_pid(pidfile)
        self.assertEqual(raised.exception.reason, "timeout")
        self.assertFalse(raised.exception.cleanup_failed)
        self.assertEqual(stopped.read_text(), "stopped")
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_sigterm_ignoring_process_requires_kill(self):
        ready = self.directory / "ready"
        leader = self.script("ignores_term.py", f'''
            import signal, time
            from pathlib import Path
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            Path({str(ready)!r}).write_text("ready")
            while True:
                time.sleep(0.01)
        ''')
        started = time.monotonic()
        with self.assertRaises(BackupProcessError) as raised:
            run_monitored_command(self.command(leader), timeout=0.3,
                                  stop_timeout=0.1, kill_timeout=0.3,
                                  check_interval=0.01)
        self.assertTrue(ready.exists())
        self.assertEqual(raised.exception.returncode, -signal.SIGKILL)
        self.assertFalse(raised.exception.cleanup_failed)
        self.assertLess(time.monotonic() - started, 2)

    def test_health_failure_cleans_up_real_process(self):
        pidfile = self.directory / "leader.pid"
        leader = self.script("health.py", f'''
            import os, time
            from pathlib import Path
            Path({str(pidfile)!r} + ".tmp").write_text(str(os.getpid()))
            os.replace({str(pidfile)!r} + ".tmp", {str(pidfile)!r})
            while True:
                time.sleep(0.01)
        ''')

        def health():
            if pidfile.exists():
                raise StorageUnavailableError("simulated mount identity changed")

        with self.assertRaises(StorageUnavailableError):
            run_monitored_command(self.command(leader), timeout=2,
                                  health_check=health, check_interval=0.01)
        pid = self.read_pid(pidfile)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_leader_exit_cannot_report_success_with_live_group_descendant(self):
        pidfile = self.directory / "orphan.pid"
        stopped = self.directory / "orphan.stopped"
        child = self.script("orphan.py", f'''
            import os, signal, time
            from pathlib import Path
            def stop(*_args):
                Path({str(stopped)!r}).write_text("stopped")
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop)
            Path({str(pidfile)!r} + ".tmp").write_text(str(os.getpid()))
            os.replace({str(pidfile)!r} + ".tmp", {str(pidfile)!r})
            while True:
                time.sleep(0.01)
        ''')
        leader = self.script("exits.py", f'''
            import subprocess, sys, time
            from pathlib import Path
            subprocess.Popen([sys.executable, {str(child)!r}])
            while not Path({str(pidfile)!r}).exists():
                time.sleep(0.01)
        ''')
        with self.assertRaises(BackupProcessError) as raised:
            run_monitored_command(self.command(leader), timeout=2,
                                  check_interval=0.01, stop_timeout=0.2,
                                  kill_timeout=0.2)
        self.read_pid(pidfile)
        self.assertEqual(raised.exception.reason, "descendants")
        self.assertEqual(stopped.read_text(), "stopped")

    def test_repeated_interrupts_do_not_abort_forced_cleanup(self):
        pidfile = self.directory / "repeated.pid"
        result = self.directory / "repeated.result"
        leader = self.script("repeated-child.py", f'''
            import os, signal, time
            from pathlib import Path
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            Path({str(pidfile)!r} + ".tmp").write_text(str(os.getpid()))
            os.replace({str(pidfile)!r} + ".tmp", {str(pidfile)!r})
            while True:
                time.sleep(0.01)
        ''')
        supervisor = self.script("repeated-supervisor.py", f'''
            import sys
            from pathlib import Path
            from iphone_backup_cli.backup_process import (
                BackupProcessInterruptedError, run_monitored_command,
            )
            try:
                run_monitored_command([sys.executable, {str(leader)!r}],
                                      check_interval=0.01, stop_timeout=0.4,
                                      kill_timeout=0.5)
            except BackupProcessInterruptedError as error:
                assert not error.cleanup_failed
                Path({str(result)!r}).write_text("cleaned")
        ''')
        process = subprocess.Popen(self.command(supervisor))
        self.supervisors.append(process)
        try:
            deadline = time.monotonic() + 3
            while not pidfile.exists() and process.poll() is None:
                if time.monotonic() >= deadline:
                    self.fail("Fixture child did not become ready")
                time.sleep(0.01)
            pid = self.read_pid(pidfile)
            process.send_signal(signal.SIGTERM)
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGINT):
                time.sleep(0.04)
                process.send_signal(signum)
            self.assertEqual(process.wait(timeout=3), 0)
            self.assertEqual(result.read_text(), "cleaned")
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        finally:
            self.stop_supervisor(process)

    def test_pinned_descriptor_reaches_child_without_other_inherited_descriptors(self):
        target = self.directory / "descriptor-output"
        unintended = self.directory / "must-not-be-written"
        descriptor = os.open(target, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        other = os.open(unintended, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        os.set_inheritable(other, True)
        leader = self.script("descriptor.py", f'''
            import os
            os.write({descriptor}, b"pinned")
            try:
                os.write({other}, b"leaked")
            except OSError:
                pass
            else:
                raise SystemExit(3)
        ''')
        try:
            self.assertEqual(run_monitored_command(self.command(leader),
                                                   pass_fds=(descriptor,)), 0)
            os.fstat(descriptor)  # The caller retains ownership.
        finally:
            os.close(descriptor)
            os.close(other)
        self.assertEqual(target.read_bytes(), b"pinned")
        self.assertEqual(unintended.read_bytes(), b"")

    def test_sigint_and_sigterm_clean_up_and_restore_supervisor_handlers(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signum=signum):
                pidfile = self.directory / f"signal-{signum}.pid"
                result = self.directory / f"signal-{signum}.result"
                leader = self.script(f"signal-child-{signum}.py", f'''
                    import os, time
                    from pathlib import Path
                    Path({str(pidfile)!r} + ".tmp").write_text(str(os.getpid()))
                    os.replace({str(pidfile)!r} + ".tmp", {str(pidfile)!r})
                    while True:
                        time.sleep(0.01)
                ''')
                supervisor = self.script(f"supervisor-{signum}.py", f'''
                    import signal, sys
                    from pathlib import Path
                    from iphone_backup_cli.backup_process import (
                        BackupProcessInterruptedError, run_monitored_command,
                    )
                    before = {{s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}}
                    try:
                        run_monitored_command([sys.executable, {str(leader)!r}],
                                              check_interval=0.01)
                    except KeyboardInterrupt:
                        outcome = "interrupt"
                    except BackupProcessInterruptedError:
                        outcome = "terminate"
                    else:
                        outcome = "unexpected-success"
                    assert before == {{s: signal.getsignal(s) for s in before}}
                    Path({str(result)!r}).write_text(outcome)
                ''')
                process = subprocess.Popen(self.command(supervisor))
                self.supervisors.append(process)
                try:
                    deadline = time.monotonic() + 3
                    while not pidfile.exists() and process.poll() is None:
                        if time.monotonic() >= deadline:
                            self.fail("Fixture child did not become ready")
                        time.sleep(0.01)
                    pid = self.read_pid(pidfile)
                    process.send_signal(signum)
                    self.assertEqual(process.wait(timeout=3), 0)
                    self.assertEqual(result.read_text(),
                                     "interrupt" if signum == signal.SIGINT else "terminate")
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
                finally:
                    self.stop_supervisor(process)


if __name__ == "__main__":
    unittest.main()
