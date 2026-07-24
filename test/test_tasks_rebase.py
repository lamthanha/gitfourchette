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


def testRebaseBannerDetachedHead(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    runShellScript(
        """
        git switch --detach feature
        git rebase master || true
        """,
        wd)
    rw = mainWindow.openRepo(wd)

    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.mergeBanner.isVisibleTo(rw)
    labelText = rw.mergeBanner.label.text()
    assert re.search(r"rebasing", labelText, re.I)
    # rebase-merge/head-name contains "detached HEAD" -- must not leak into the title
    assert not re.search(r"detached", labelText, re.I)


def testRebaseOntoAncestorIsUpToDate(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c feature master
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        """,
        wd)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target
    oldTip = rw.repo.branches.local["feature"].target

    rw.jump(NavLocator.inCommit(masterTip))
    # Clean tree, ahead of master: rebases immediately -- git reports "up to date"
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["feature"].target == oldTip
    assert re.search(r"up to date", mainWindow.statusBar().currentMessage(), re.I)


def testRebaseDirtyAutostashUnchecked(tempDir, mainWindow):
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
    oldTip = rw.repo.branches.local["feature"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    qmb = findQMessageBox(rw, r"rebase.+feature.+onto")
    qmb.checkBox().setChecked(False)  # decline autostash
    qmb.accept()

    # git refuses to rebase a dirty tree without autostash; error is surfaced
    acceptQMessageBox(rw, r"unstaged|uncommitted|cannot")
    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["feature"].target == oldTip
    assert readFile(f"{wd}/notes.txt").decode() == "notes dirty\n"


def testRebaseSidebarEntryDisabledForCurrentBranch(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/feature")  # the checked-out branch
    menu = rw.sidebar.makeNodeMenu(node)
    action = findMenuAction(menu, r"rebase.+onto")
    assert not action.isEnabled()


def makeLinearHistory(tempDir) -> str:
    """Branch 'work' with three independent commits (each touches its own
    file), so any reordering replays cleanly. Newest commit: 'ir: three'."""
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c work master
        echo one > one.txt
        git add one.txt
        git commit -m "ir: one"
        echo two > two.txt
        git add two.txt
        git commit -m "ir: two"
        echo three > three.txt
        git add three.txt
        git commit -m "ir: three"
        """,
        wd)
    return wd


def _commitIdByMessage(repo, prefix: str):
    return next(c.id for c in repo.walk(repo.head_commit_id)
                if c.message.startswith(prefix))


def _logSummaries(repo, n: int) -> list[str]:
    summaries = []
    for commit in repo.walk(repo.head_commit_id):
        if len(summaries) == n:
            break
        summaries.append(commit.message.splitlines()[0])
    return summaries


def _openTodoDialog(rw, fromPrefix: str):
    fromId = _commitIdByMessage(rw.repo, fromPrefix)
    rw.jump(NavLocator.inCommit(fromId))
    triggerContextMenuAction(rw.graphView.viewport(), r"interactive rebase")
    return findQDialog(rw, r"interactive rebase")


def testInteractiveRebaseReorder(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    assert [r.summary for r in dlg.rows()] == ["ir: three", "ir: two", "ir: one"]
    assert not dlg.autostash()  # clean tree: no autostash offer
    dlg.moveRow(0, 1)  # "three" now executes before "two"
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 3) == ["ir: two", "ir: three", "ir: one"]
    headTree = rw.repo.peel_commit(rw.repo.head_commit_id).tree
    for name in ("one.txt", "two.txt", "three.txt"):
        assert name in headTree
    # Success jumps the view to the rebased HEAD
    assert rw.navLocator.commit == rw.repo.head_commit_id


def testInteractiveRebaseDrop(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "drop")  # drop "ir: two"
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: three", "ir: one"]
    headTree = rw.repo.peel_commit(rw.repo.head_commit_id).tree
    assert "two.txt" not in headTree
    assert "three.txt" in headTree


def testInteractiveRebaseSquashWithEditedMessage(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "squash")  # "ir: two" folds into "ir: one"
    dlg.setMessage(1, "ir: one and two combined\n\nSquashed by test.")
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: three", "ir: one and two combined"]
    combined = rw.repo.peel_commit(rw.repo.head_commit_id).parents[0]
    assert "Squashed by test." in combined.message
    assert "one.txt" in combined.tree
    assert "two.txt" in combined.tree


def testInteractiveRebaseFixup(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "fixup")  # "ir: two" melds into "ir: one", message discarded
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: three", "ir: one"]
    combined = rw.repo.peel_commit(rw.repo.head_commit_id).parents[0]
    assert "two.txt" in combined.tree


def testInteractiveRebaseReword(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "reword")
    dlg.setMessage(1, "ir: two (reworded)\n\nMore detail.")
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 3) == ["ir: three", "ir: two (reworded)", "ir: one"]
    reworded = rw.repo.peel_commit(rw.repo.head_commit_id).parents[0]
    assert "More detail." in reworded.message


def makeDependentHistory(tempDir) -> str:
    """Branch 'work' where 'ir: beta' depends on 'ir: alpha' (same file),
    so dropping alpha makes beta conflict; 'ir: own' is independent."""
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c work master
        echo base > shared.txt
        git add shared.txt
        git commit -m "ir: base"
        echo alpha > shared.txt
        git add shared.txt
        git commit -m "ir: alpha"
        echo beta > shared.txt
        git add shared.txt
        git commit -m "ir: beta"
        echo own > own.txt
        git add own.txt
        git commit -m "ir: own"
        """,
        wd)
    return wd


def testInteractiveRebaseConflictResolveContinue(tempDir, mainWindow):
    wd = makeDependentHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: alpha")
    assert [r.summary for r in dlg.rows()] == ["ir: own", "ir: beta", "ir: alpha"]
    dlg.setAction(2, "drop")  # drop alpha -> beta conflicts at step 1 of 2
    dlg.accept()

    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.repo.any_conflicts
    assert rw.mergeBanner.isVisibleTo(rw)

    # Resolve by taking THEIRS (the replayed commit's version: "beta")
    rw.jump(NavLocator.inUnstaged("shared.txt"))
    assert rw.conflictView.isVisibleTo(rw)
    rw.conflictView.ui.theirsButton.click()

    _bannerButton(rw, r"continue").click()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: own", "ir: beta"]
    assert readFile(f"{wd}/shared.txt").decode().strip() == "beta"
    headTree = rw.repo.peel_commit(rw.repo.head_commit_id).tree
    assert "own.txt" in headTree


def testInteractiveRebaseAbortRestoresBranch(tempDir, mainWindow):
    wd = makeDependentHistory(tempDir)
    rw = mainWindow.openRepo(wd)
    oldTip = rw.repo.branches.local["work"].target

    dlg = _openTodoDialog(rw, "ir: alpha")
    dlg.setAction(2, "drop")
    dlg.accept()
    assert rw.repo.state() in REBASE_STATES_FOR_TESTS

    _bannerButton(rw, r"abort").click()
    acceptQMessageBox(rw, r"abort.+rebase")

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["work"].target == oldTip


def testInteractiveRebaseCancelDialog(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)
    oldTip = rw.repo.branches.local["work"].target

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.reject()

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["work"].target == oldTip


def testInteractiveRebaseWarnsAboutFlattenedMerges(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c work master
        echo one > one.txt
        git add one.txt
        git commit -m "ir: one"
        git switch -c side
        echo side > side.txt
        git add side.txt
        git commit -m "side: extra"
        git switch work
        echo two > two.txt
        git add two.txt
        git commit -m "ir: two"
        git merge side -m "merge side into work"
        """,
        wd)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    summaries = [r.summary for r in dlg.rows()]
    assert "merge side into work" not in summaries  # merge commit excluded
    assert set(summaries) == {"ir: two", "side: extra", "ir: one"}
    assert summaries[-1] == "ir: one"  # oldest at the bottom
    assert dlg.mergeWarningLabel.isVisibleTo(dlg)
    dlg.reject()  # don't execute; flattening semantics are git's own

    assert rw.repo.state() == RepositoryState.NONE


def testInteractiveRebaseDirtyAutostash(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    writeFile(f"{wd}/one.txt", "one dirty\n")  # tracked file, uncommitted change
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    assert dlg.autostashCheckBox.isVisibleTo(dlg)
    assert dlg.autostash()
    dlg.moveRow(0, 1)
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.repo.any_conflicts
    assert _logSummaries(rw.repo, 3) == ["ir: two", "ir: three", "ir: one"]
    # The dirty change survived the autostash round-trip; no stash left behind
    assert readFile(f"{wd}/one.txt").decode() == "one dirty\n"
    assert len(rw.repo.listall_stashes()) == 0


def testInteractiveRebaseRewordAndSquashTogether(tempDir, mainWindow):
    # Two editor invocations in one rebase: reword fires first (when its
    # commit is applied), then the squash-chain prompt. Pins the msg-N
    # queue alignment against git's invocation order.
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(2, "reword")  # "ir: one" (first executed)
    dlg.setMessage(2, "ir: one (reworded)\n\nBody R.")
    dlg.setAction(0, "squash")  # "ir: three" folds into "ir: two"
    dlg.setMessage(0, "ir: two and three\n\nBody S.")
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: two and three", "ir: one (reworded)"]
    head = rw.repo.peel_commit(rw.repo.head_commit_id)
    assert "Body S." in head.message
    assert "Body R." in head.parents[0].message
    for name in ("one.txt", "two.txt", "three.txt"):
        assert name in head.tree
