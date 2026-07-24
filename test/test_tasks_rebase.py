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
    # Clean worktree: Fork-style flow rebases immediately, no confirm dialog
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")

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

    assert rw.repo.state() in (
        RepositoryState.REBASE,
        RepositoryState.REBASE_INTERACTIVE,
        RepositoryState.REBASE_MERGE)
    assert rw.repo.any_conflicts


def _bannerButton(rw, pattern: str):
    # Newly-added banner buttons need one event loop tick before Qt marks
    # them visible (same as pre-existing merge/cherry-pick/revert banner
    # buttons) -- pump the queue so isVisibleTo() reflects the real state.
    QTest.qWait(0)
    return next((b for b in rw.mergeBanner.buttons
                 if re.search(pattern, b.text(), re.I) and b.isVisibleTo(rw)), None)


def _startConflictedRebase(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target
    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.mergeBanner.isVisibleTo(rw)
    assert re.search(r"rebasing", rw.mergeBanner.label.text(), re.I)
    return rw


REBASE_STATES_FOR_TESTS = (
    RepositoryState.REBASE,
    RepositoryState.REBASE_INTERACTIVE,
    RepositoryState.REBASE_MERGE)


def testRebaseConflictBannerAndAbort(tempDir, mainWindow):
    rw = _startConflictedRebase(tempDir, mainWindow)
    oldFeatureTip = rw.repo.branches.local["feature"].target

    _bannerButton(rw, r"abort").click()
    acceptQMessageBox(rw, r"abort.+rebase")

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.mergeBanner.isVisibleTo(rw)
    assert rw.repo.branches.local["feature"].target == oldFeatureTip


def testRebaseConflictResolveAndContinue(tempDir, mainWindow):
    rw = _startConflictedRebase(tempDir, mainWindow)
    masterTip = rw.repo.branches.local["master"].target

    # Resolve the conflict by taking THEIRS (the feature branch's version)
    rw.jump(NavLocator.inUnstaged("clash.txt"))
    assert rw.conflictView.isVisibleTo(rw)
    rw.conflictView.ui.theirsButton.click()

    _bannerButton(rw, r"continue").click()

    assert rw.repo.state() == RepositoryState.NONE
    newTip = rw.repo.peel_commit(rw.repo.branches.local["feature"].target)
    assert newTip.message.startswith("feature: own file")
    # Rebased chain sits on top of master's tip
    assert newTip.parents[0].parents[0].id == masterTip


def testRebaseSkipCommit(tempDir, mainWindow):
    rw = _startConflictedRebase(tempDir, mainWindow)
    masterTip = rw.repo.branches.local["master"].target

    _bannerButton(rw, r"skip").click()
    acceptQMessageBox(rw, r"skip")

    assert rw.repo.state() == RepositoryState.NONE
    newTip = rw.repo.peel_commit(rw.repo.branches.local["feature"].target)
    # The conflicting commit was skipped; only "feature: own file" remains
    assert newTip.message.startswith("feature: own file")
    assert newTip.parents[0].id == masterTip


def testRebaseStartedOutsideApp(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    runShellScript("git rebase master || true", wd)
    rw = mainWindow.openRepo(wd)

    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.mergeBanner.isVisibleTo(rw)
    assert re.search(r"rebasing", rw.mergeBanner.label.text(), re.I)
    for pattern in (r"continue", r"skip", r"abort"):
        assert _bannerButton(rw, pattern) is not None


def testRebaseAutostashPopConflict(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch master
        echo "base" > shared.txt
        git add shared.txt
        git commit -m "base: shared"
        git switch -c feature
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        git switch master
        echo "master version" > shared.txt
        git add shared.txt
        git commit -m "master: shared"
        git switch feature
        echo "dirty version" > shared.txt
        """,
        wd)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"rebase.+feature.+onto")

    # The rebase itself completed...
    assert rw.repo.state() == RepositoryState.NONE
    newTip = rw.repo.peel_commit(rw.repo.branches.local["feature"].target)
    assert newTip.message.startswith("feature: own file")
    assert newTip.parents[0].id == masterTip
    # ...but popping the autostash conflicted; the changes survive in the stash
    assert rw.repo.any_conflicts
    assert len(rw.repo.listall_stashes()) == 1
    # The fix jumps the user to the workdir so they see the conflicts
    assert rw.navLocator.context.isWorkdir()


def testRebaseOntoFromSidebar(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"rebase.+feature.+onto")

    # Divergent scenario conflicts, so we should now be mid-rebase
    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    # HEAD sits at the rebase target while paused on the first replayed commit
    assert rw.repo.head_commit_id == masterTip


def testRebaseOntoBranchCheckedOutInOtherWorktree(tempDir, mainWindow):
    # Rebasing onto a branch never touches that branch's checkout, so the
    # sidebar entry must stay enabled even when the target branch is checked
    # out in a linked worktree (pygit2's is_checked_out is worktree-wide).
    wd = makeDivergentBranches(tempDir)
    runShellScript("git worktree add ../linked-wt master", wd)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"rebase.+feature.+onto")
    assert rw.repo.state() in REBASE_STATES_FOR_TESTS


def testRebaseDirtyShowsDialogAndAutostashReapplies(tempDir, mainWindow):
    # A dirty worktree is the only case that shows the confirm dialog
    # (Fork-style flow); autostash must reapply the changes after the rebase.
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch master
        echo "notes" > notes.txt
        git add notes.txt
        git commit -m "base: notes"
        git switch -c feature
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        git switch master
        echo "master only" > master.txt
        git add master.txt
        git commit -m "master: own file"
        git switch feature
        echo "notes dirty" > notes.txt
        """,
        wd)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"rebase.+feature.+onto")

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.repo.any_conflicts
    newTip = rw.repo.peel_commit(rw.repo.branches.local["feature"].target)
    assert newTip.message.startswith("feature: own file")
    assert newTip.parents[0].id == masterTip
    # The dirty change survived the autostash round-trip; no stash left behind
    assert readFile(f"{wd}/notes.txt").decode() == "notes dirty\n"
    assert len(rw.repo.listall_stashes()) == 0
