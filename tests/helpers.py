"""Shared fixtures: a scratch ledger, a captured console and scripted prompts.

Every feature in the tracker talks to the user through `rich` prompts and
writes to `DATA_FILE`, so a test needs three things redirected: the data file
to a temporary directory, `console` to a string buffer, and `Prompt.ask` /
`Confirm.ask` to a list of answers. `Session` does all three for whichever
module it is given, so the same scenario can be run against the current code
and against the original read out of git.
"""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rich.console import Console

import budget_tracker
import original

HEADER = "date,type,category,description,amount\r\n"


class OutOfAnswers(AssertionError):
    """The code under test asked more questions than the test scripted."""


class Session:
    """Run a module's functions against a scratch ledger with scripted input."""

    def __init__(self, module, directory):
        self.m = module
        self.dir = Path(directory)
        self.data_file = self.dir / "budget_data.csv"
        self.buffer = io.StringIO()

    def path(self, name):
        return str(self.dir / name)

    def write(self, name, text, encoding="utf-8"):
        with open(self.dir / name, "w", newline="", encoding=encoding) as f:
            f.write(text)
        return self.path(name)

    def write_ledger(self, text):
        return self.write("budget_data.csv", text)

    def ledger_text(self):
        with open(self.data_file, newline="", encoding="utf-8") as f:
            return f.read()

    @property
    def output(self):
        return self.buffer.getvalue()

    @contextlib.contextmanager
    def active(self, answers=(), confirms=()):
        """Redirect the module's data file, console and prompts for a block."""
        answers, confirms = list(answers), list(confirms)

        def ask(*args, **kwargs):
            if not answers:
                raise OutOfAnswers(f"unscripted prompt: {args[1:] or args}")
            return answers.pop(0)

        def confirm(*args, **kwargs):
            if not confirms:
                raise OutOfAnswers(f"unscripted confirmation: {args[1:] or args}")
            return confirms.pop(0)

        console = Console(file=self.buffer, width=160, color_system=None,
                          force_terminal=False, legacy_windows=False)
        with mock.patch.object(self.m, "DATA_FILE", str(self.data_file)), \
                mock.patch.object(self.m, "console", console), \
                mock.patch.object(self.m.Prompt, "ask", side_effect=ask), \
                mock.patch.object(self.m.Confirm, "ask", side_effect=confirm):
            yield self
        self.unused_answers = answers

    def call(self, name, *args, answers=(), confirms=()):
        with self.active(answers, confirms):
            return getattr(self.m, name)(*args)


class LedgerCase(unittest.TestCase):
    """A test case with a fresh scratch directory per test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="budget-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def session(self, module=None):
        module = module or budget_tracker
        directory = os.path.join(self.tmp, module.__name__)
        os.makedirs(directory, exist_ok=True)
        return Session(module, directory)


class RegressionCase(LedgerCase):
    """Every scenario is a function of a `Session`, and each test runs it
    twice -- once against the baseline module read out of git by
    `original.py`, once against the current one -- and asserts the original
    shows the defect. A scenario the original survives is testing nothing, so
    that half is not optional: without the baseline, the test skips."""

    def both(self, scenario):
        """Run a scenario against the original and the current code."""
        orig = original.require()
        return scenario(self.session(orig)), scenario(self.session(budget_tracker))

    @staticmethod
    def outcome(fn):
        """The value of fn(), or the exception it raised, for comparison."""
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 -- the exception *is* the observation
            return e
