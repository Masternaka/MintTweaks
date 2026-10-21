"""Tests for the command layer."""

import os
import subprocess
import sys
import unittest
from unittest import mock

from minttweaks.core.privilege import ENV_OVERRIDE, Escalator, is_root
from minttweaks.core.runner import (
    RC_NOT_ALLOWED,
    RC_NOT_FOUND,
    Command,
    SubprocessRunner,
    cmd,
    coerce,
)

PYTHON = sys.executable or "python3"


def plain_runner() -> SubprocessRunner:
    return SubprocessRunner(escalator=Escalator(prefix=[]))


class CommandTests(unittest.TestCase):
    def test_render_is_shell_quoted(self):
        self.assertEqual(str(cmd("apt-get", "install", "a b")), "apt-get install 'a b'")

    def test_root_commands_are_rendered_with_sudo(self):
        self.assertTrue(str(cmd("apt-get", "update", root=True)).startswith("sudo "))

    def test_empty_command_is_rejected(self):
        with self.assertRaises(ValueError):
            Command(())

    def test_nul_bytes_are_rejected(self):
        with self.assertRaises(ValueError):
            Command(("echo", "a\x00b"))

    def test_non_string_arguments_are_rejected(self):
        with self.assertRaises(TypeError):
            Command(("echo", 42))

    def test_strings_are_not_accepted_as_argv(self):
        with self.assertRaises(TypeError):
            coerce("echo hello")


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.runner = plain_runner()

    def test_success(self):
        result = self.runner.run(cmd(PYTHON, "-c", "print('hello')"))
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout.strip(), "hello")

    def test_failure_keeps_output(self):
        result = self.runner.run(cmd(PYTHON, "-c", "import sys; sys.exit(3)"))
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 3)

    def test_missing_program(self):
        result = self.runner.run(cmd("definitely-not-a-program-xyz"))
        self.assertEqual(result.returncode, RC_NOT_FOUND)
        self.assertIn("Program not found", result.stderr)

    def test_stdin_is_forwarded(self):
        result = self.runner.run(cmd(PYTHON, "-c", "import sys; print(sys.stdin.read().strip())"),
                                 input_text="secret\n")
        self.assertEqual(result.stdout.strip(), "secret")

    def test_environment_is_forced_to_c_locale(self):
        result = self.runner.run(cmd(PYTHON, "-c", "import os; print(os.environ['LC_ALL'])"))
        self.assertEqual(result.stdout.strip(), "C")

    def test_timeout(self):
        result = self.runner.run(cmd(PYTHON, "-c", "import time; time.sleep(5)"), timeout=0.2)
        self.assertFalse(result.ok)

    def test_stream_delivers_lines(self):
        seen = []
        result = self.runner.stream(
            cmd(PYTHON, "-c", "print('one'); print('two')"), on_line=seen.append
        )
        self.assertTrue(result.ok)
        self.assertEqual(seen, ["one", "two"])

    def test_stream_stops_when_the_callback_returns_false(self):
        seen = []

        def stop_after_first(line):
            seen.append(line)
            return False

        self.runner.stream(cmd(PYTHON, "-c", "print('a'); print('b')"), on_line=stop_after_first)
        self.assertEqual(seen, ["a"])

    def test_stream_missing_program(self):
        result = self.runner.stream(cmd("definitely-not-a-program-xyz"))
        self.assertEqual(result.returncode, RC_NOT_FOUND)

    def test_dry_run_runs_nothing(self):
        runner = SubprocessRunner(escalator=Escalator(prefix=[]), dry_run=True)
        result = runner.run(cmd("this-would-fail-if-executed"))
        self.assertTrue(result.ok)
        self.assertIn("dry-run", result.stdout)


class EscalationTests(unittest.TestCase):
    def test_prefix_is_applied_only_to_root_commands(self):
        escalator = Escalator(prefix=["sudo", "-n"])
        self.assertEqual(escalator.wrap(["ls"], needs_root=False), ["ls"])
        wrapped = escalator.wrap(["id"], needs_root=True)
        if is_root():
            self.assertEqual(wrapped, ["id"])
        else:
            self.assertEqual(wrapped[0:2], ["sudo", "-n"])
            self.assertTrue(wrapped[2].endswith("/id") or wrapped[2] == "id")

    def test_program_is_made_absolute_for_pkexec(self):
        escalator = Escalator(prefix=["pkexec"])
        wrapped = escalator.wrap(["sh", "-c", "id"], needs_root=True)
        self.assertTrue(os.path.isabs(wrapped[1]), wrapped)

    def test_disabled_escalation_returns_a_clear_error(self):
        runner = SubprocessRunner(escalator=Escalator(prefix=[]))
        if is_root():
            self.skipTest("root needs no escalation")
        result = runner.run(cmd("id", root=True))
        self.assertEqual(result.returncode, RC_NOT_ALLOWED)
        self.assertIn("administrator rights", result.stderr)

    def test_environment_override_is_honoured(self):
        with mock.patch.dict(os.environ, {ENV_OVERRIDE: "sudo -n"}, clear=False):
            self.assertEqual(Escalator().prefix, ["sudo", "-n"])

    def test_available_reports_missing_binary(self):
        self.assertFalse(Escalator(prefix=["definitely-not-a-program-xyz"]).available())

    def test_no_nesting_when_already_root(self):
        escalator = Escalator(prefix=["pkexec"])
        argv = escalator.wrap(["true"], needs_root=True)
        if is_root():
            self.assertEqual(argv, ["true"])
        else:
            self.assertEqual(argv[0], "pkexec")


class ReprTests(unittest.TestCase):
    def test_result_output_combines_streams(self):
        from minttweaks.core.runner import Result

        result = Result("cmd", 1, stdout="out\n", stderr="err\n")
        self.assertEqual(result.output, "out\nerr")
        self.assertTrue(result.failed_with_missing_program() is False)

    def test_describe(self):
        from minttweaks.core.runner import Result, describe

        self.assertIn("ok", describe(Result("x", 0)))
        self.assertIn("failed", describe(Result("x", 2)))


class SubprocessSanityTests(unittest.TestCase):
    """Guard against accidentally shipping code that shells out."""

    def test_runner_does_not_use_shell_true(self):
        from minttweaks.core import runner as runner_module

        with open(runner_module.__file__, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("shell=True", source)
        self.assertEqual(subprocess.list2cmdline([]), "")


if __name__ == "__main__":
    unittest.main()
