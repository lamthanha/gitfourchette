# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import re

from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from .util import *


def makeDivergentBranches(tempDir) -> str:
    """Unpack a canned repo, then create branch 'feature' diverging from
    'master': both add a commit touching clash.txt with different content.
    Leaves 'feature' checked out. Returns the workdir path."""
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c feature master
        echo "feature version" > clash.txt
        git add clash.txt
        git commit -m "feature: clash"
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        git switch master
        echo "master version" > clash.txt
        git add clash.txt
        git commit -m "master: clash"
        git switch feature
        """,
        wd)
    return wd


def testRebaseOntoClean(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c feature master
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        git switch master
        echo "master only" > master.txt
        git add master.txt
        git commit -m "master: own file"
        git switch feature
        """,
        wd)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target
    oldFeatureTip = rw.repo.branches.local["feature"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"rebase.+feature.+onto")

    assert rw.repo.state() == RepositoryState.NONE
    newTip = rw.repo.branches.local["feature"].target
    assert newTip != oldFeatureTip
    newTipCommit = rw.repo.peel_commit(newTip)
    assert newTipCommit.message.startswith("feature: own file")
    assert newTipCommit.parents[0].id == masterTip


def testRebaseOntoNothingToDo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    headId = rw.repo.head_commit_id

    rw.jump(NavLocator.inCommit(headId))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"nothing to rebase")
    assert rw.repo.state() == RepositoryState.NONE


def testRebaseOntoConflict(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"rebase.+feature.+onto")

    assert rw.repo.state() in (
        RepositoryState.REBASE,
        RepositoryState.REBASE_INTERACTIVE,
        RepositoryState.REBASE_MERGE)
    assert rw.repo.any_conflicts
