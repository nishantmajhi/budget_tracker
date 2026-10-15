"""Load the pre-cleanup program, so a regression test can be shown failing.

The original is one self-contained module that does nothing at import time,
so there is nothing to transcribe: the baseline commit is read straight out of
git, written to a scratch file and imported under its own name.

The baseline is found by its commit subject rather than by hash, so the tests
survive the branch being rebased. If it cannot be found -- a copy with no git
directory, say -- every test that needs it skips rather than fails.
"""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASELINE_SUBJECT = "Initial commit"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_cache = {}


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout


def baseline_commit():
    """The commit the cleanup started from, looked up by its subject."""
    matches = [
        line.split(" ", 1)[0]
        for line in _git("log", "--format=%H %s").splitlines()
        if line.split(" ", 1)[1:] == [BASELINE_SUBJECT]
    ]
    if len(matches) != 1:
        raise LookupError(
            f"expected exactly one commit titled {BASELINE_SUBJECT!r}, found {len(matches)}"
        )
    return matches[0]


def load():
    """Import the baseline `budget_tracker.py` as a module object."""
    if "module" in _cache:
        return _cache["module"]
    try:
        source = _git("show", f"{baseline_commit()}:budget_tracker.py")
    except (OSError, subprocess.CalledProcessError, LookupError) as e:
        _cache["module"] = None
        _cache["why"] = str(e)
        return None
    scratch = Path(tempfile.mkdtemp(prefix="budget-baseline-")) / "original_budget_tracker.py"
    scratch.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("original_budget_tracker", scratch)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _cache["module"] = module
    return module


def require():
    """The baseline module, or skip the calling test if it is unavailable."""
    module = load()
    if module is None:
        raise unittest.SkipTest(f"baseline not available: {_cache.get('why')}")
    return module
