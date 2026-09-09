# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension tests — GitDriver exit-code reporting.
# -----------------------------------------------------------------------------

import pytest

from gitfourchette.gitdriver import GitDriver
from gitfourchette.qt import *


def _runShell(script: str) -> GitDriver:
    """Drive a GitDriver over /bin/sh so the exit condition is exact.
    (formatExitCode only reads exitCode/exitStatus, not the command line.)"""
    driver = GitDriver()
    driver.setProgram("/bin/sh")
    driver.setArguments(["-c", script])
    driver.start()
    assert driver.waitForFinished(10000)
    return driver


@pytest.mark.skipif(WINDOWS, reason="POSIX signal semantics")
@pytest.mark.parametrize("code", [1, 2, 9, 15, 31])
def testFormatExitCodeDoesNotInventSignalNames(qapp, code):
    # A process that EXITS with status N wasn't killed by signal N. Naming
    # signals here made every ordinary git failure read as a crash --
    # `git merge --ff-only` declining a dirty worktree exits 1, which is
    # not SIGHUP.
    driver = _runShell(f"exit {code}")
    assert driver.exitStatus() == QProcess.ExitStatus.NormalExit
    assert driver.formatExitCode() == str(code)


@pytest.mark.skipif(WINDOWS, reason="POSIX signal semantics")
def testFormatExitCodeNamesSignalOnCrash(qapp):
    # Genuinely killed by a signal: Qt reports CrashExit and puts the signal
    # number in exitCode(). That's when the name is informative.
    driver = _runShell("kill -TERM $$; sleep 10")
    assert driver.exitStatus() == QProcess.ExitStatus.CrashExit
    assert driver.formatExitCode() == "15 (SIGTERM)"
