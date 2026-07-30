# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension tests — Phase 3 worktree management.
# -----------------------------------------------------------------------------

import os

import pytest

from gitfourchette import worktrees
from gitfourchette.sidebar.sidebarmodel import SidebarItem, SidebarModel
from .util import *

SAMPLE_PORCELAIN = """\
worktree /home/u/repo
HEAD 1111111111111111111111111111111111111111
branch refs/heads/master

worktree /home/u/repo-feature
HEAD 2222222222222222222222222222222222222222
branch refs/heads/feature

worktree /home/u/repo-detached
HEAD 3333333333333333333333333333333333333333
detached

worktree /home/u/repo-locked
HEAD 4444444444444444444444444444444444444444
branch refs/heads/locky
locked demo of a lock reason

worktree /home/u/repo-gone
HEAD 5555555555555555555555555555555555555555
branch refs/heads/gone
prunable gitdir file points to non-existent location
"""

BARE_PORCELAIN = """\
worktree /home/u/bare.git
bare

worktree /home/u/wt
HEAD 6666666666666666666666666666666666666666
branch refs/heads/main
"""


def testParseWorktreeListPorcelain():
    infos = worktrees.parseWorktreeListPorcelain(SAMPLE_PORCELAIN)
    assert [wt.path for wt in infos] == [
        "/home/u/repo", "/home/u/repo-feature", "/home/u/repo-detached",
        "/home/u/repo-locked", "/home/u/repo-gone"]
    assert [wt.isMain for wt in infos] == [True, False, False, False, False]
    main = infos[0]
    assert main.branch == "refs/heads/master"
    assert main.head.startswith("1111")
    assert not (main.isBare or main.isDetached or main.locked or main.prunable)
    detached = infos[2]
    assert detached.isDetached and detached.branch == ""
    locked = infos[3]
    assert locked.locked and locked.lockedReason == "demo of a lock reason"
    gone = infos[4]
    assert gone.prunable and "non-existent" in gone.prunableReason


def testParseWorktreeListPorcelainBareAndEmpty():
    infos = worktrees.parseWorktreeListPorcelain(BARE_PORCELAIN)
    assert infos[0].isBare and infos[0].isMain and infos[0].branch == ""
    assert not infos[1].isBare and infos[1].branch == "refs/heads/main"
    assert worktrees.parseWorktreeListPorcelain("") == []
    assert worktrees.parseWorktreeListPorcelain("\n\n") == []


def testListWorktreesRealRepo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    infos = worktrees.listWorktrees(wd)
    assert len(infos) == 1
    assert infos[0].isMain
    assert os.path.realpath(infos[0].path) == os.path.realpath(wd)

    # Use "no-parent" (not "master") because TestGitRepository is checked out
    # on master already, and git refuses to check out an already-checked-out
    # branch in a second worktree ("fatal: 'master' is already used by
    # worktree at ..."). Verified with `git branch -a` in the unpacked repo.
    runShellScript("git worktree add ../LinkedWT no-parent", wd)
    infos = worktrees.listWorktrees(wd)
    assert len(infos) == 2
    assert infos[1].branch == "refs/heads/no-parent"
    assert not infos[1].isMain

    # Listing works from the linked worktree too, and not-a-repo yields []
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    assert [wt.path for wt in worktrees.listWorktrees(linked)] == [wt.path for wt in infos]
    assert worktrees.listWorktrees(tempDir.name) == []


def testSyncWorktreesDetectsChanges(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    model = rw.repoModel
    assert len(model.worktrees) == 1  # primed at load
    assert not model.syncWorktrees()  # no change

    runShellScript("git worktree add ../LinkedWT no-parent", wd)
    assert model.syncWorktrees()      # change detected
    assert len(model.worktrees) == 2
    assert not model.syncWorktrees()  # stable again


def _openRepoWithLinkedWorktree(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT no-parent", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    rw = mainWindow.openRepo(wd)
    return wd, linked, rw


def testWorktreesSidebarSection(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    nodes = rw.sidebar.findNodesByKind(SidebarItem.Worktree)
    assert len(nodes) == 2
    assert nodes[0].parent is header

    mainNode, linkedNode = nodes
    assert os.path.realpath(mainNode.data) == os.path.realpath(wd)
    assert "(main)" not in mainNode.displayName
    assert os.path.realpath(linkedNode.data) == os.path.realpath(linked)
    assert "(main)" not in linkedNode.displayName
    assert linkedNode.displayName.startswith("LinkedWT")


def testWorktreesSectionAlwaysVisibleEvenWithoutLinked(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    assert len(header.children) == 1  # just the main worktree row


def testWorktreesListedFromLinkedWorktreeTab(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT no-parent", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    rw = mainWindow.openRepo(linked)
    nodes = rw.sidebar.findNodesByKind(SidebarItem.Worktree)
    assert len(nodes) == 2
    assert "(main)" not in nodes[0].displayName


def testOpenWorktreeInNewTab(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    assert mainWindow.tabs.count() == 1

    linkedNode = rw.sidebar.findNode(
        lambda n: n.kind == SidebarItem.Worktree and os.path.realpath(n.data) == os.path.realpath(linked))
    triggerMenuAction(rw.sidebar.makeNodeMenu(linkedNode), r"open worktree in new tab")
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(linked)

    # Double-click (wantEnterNode) opens/focuses too — no duplicate tab
    mainWindow.tabs.setCurrentIndex(0)
    rw.sidebar.wantEnterNode(linkedNode)
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(linked)


def testWorktreeSidebarRefreshAfterExternalChange(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1

    runShellScript("git worktree add ../LinkedWT no-parent", wd)
    rw.refreshRepo()  # autoRefresh path picks up external changes
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2


def testNewWorktreeExistingBranch(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "NewWT")

    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    triggerMenuAction(rw.sidebar.makeNodeMenu(header), r"new worktree")
    dlg = findQDialog(rw, r"new worktree")
    dlg.setPath(target)
    dlg.setExistingBranch("no-parent")
    dlg.accept()

    # Fork: no "open it?" offer — the new worktree's tab opens directly.
    assert os.path.isdir(target)
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(target)
    # Original tab's sidebar refreshed with the new row
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2
    # The branch is checked out there
    from gitfourchette import worktrees
    infos = worktrees.listWorktrees(wd)
    assert infos[1].branch == "refs/heads/no-parent"


def testNewWorktreeNewBranchOpensTabQuietly(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "FreshWT")

    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    triggerMenuAction(rw.sidebar.makeNodeMenu(header), r"new worktree")
    dlg = findQDialog(rw, r"new worktree")
    dlg.setPath(target)
    dlg.setNewBranch("wtbranch", "master")
    dlg.accept()

    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(target)
    assert "wtbranch" in rw.repo.branches.local


def testCheckoutBranchInNewWorktreeFromBranchMenu(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "BranchWT")

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"checkout in new worktree")
    dlg = findQDialog(rw, r"new worktree")
    assert not dlg.wantNewBranch()
    assert dlg.existingBranch() == "no-parent"  # pre-filled from the menu
    dlg.setPath(target)
    dlg.accept()

    assert mainWindow.tabs.count() == 2
    from gitfourchette import worktrees
    assert any(wt.branch == "refs/heads/no-parent" for wt in worktrees.listWorktrees(wd))


def testNewWorktreeGitFailureSurfaced(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "FailWT")

    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    dlg.setPath(target)
    dlg.setExistingBranch("master")  # master is checked out here -> git refuses
    dlg.accept()
    acceptQMessageBox(rw, r"already used by worktree|already checked out")
    assert not os.path.isdir(target)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def testNewWorktreePathPermissionErrorHandled(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    unreadableDir = os.path.join(tempDir.name, "Unreadable")
    os.mkdir(unreadableDir)
    os.chmod(unreadableDir, 0)
    try:
        from gitfourchette.tasks import NewWorktree
        NewWorktree.invoke(rw)
        dlg = findQDialog(rw, r"new worktree")
        # Point straight at the unreadable directory: listing it (Path.iterdir)
        # raises PermissionError uncaught -- this must be caught, not escape
        # into the global excepthook crash dialog. (Path.is_file()/is_dir() on
        # a nonexistent child path won't reproduce this on newer Pythons, since
        # they delegate to os.path.isfile/isdir, which already swallow OSError.)
        dlg.setPath(unreadableDir)
        assert not dlg.okButton.isEnabled()
        dlg.reject()  # cancel the task so it doesn't dangle at teardown
    finally:
        # Restore permissions so the tempdir fixture can clean up afterwards.
        os.chmod(unreadableDir, 0o755)


def _worktreeNodeByPath(rw, path):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    return rw.sidebar.findNode(
        lambda n: n.kind == SidebarItem.Worktree and os.path.realpath(n.data) == os.path.realpath(path))


def testRemoveWorktreeClean(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"remove.+worktree")

    assert not os.path.exists(linked)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1


def testRemoveWorktreeDirtyOffersForce(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    writeFile(os.path.join(linked, "dirty.txt"), "uncommitted\n")

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"remove.+worktree")
    # git refuses (dirty) -> force prompt
    acceptQMessageBox(rw, r"force")

    assert not os.path.exists(linked)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1


def testRemoveWorktreeDirtyForceDeclined(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    writeFile(os.path.join(linked, "dirty.txt"), "uncommitted\n")

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"remove.+worktree")
    rejectQMessageBox(rw, r"force")

    assert os.path.exists(linked)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2


def testRemoveMainWorktreeBlocked(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    node = _worktreeNodeByPath(rw, wd)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"main worktree")
    assert os.path.exists(os.path.normpath(wd))


def testRemoveWorktreeOpenInTabBlocked(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    mainWindow.openRepo(linked)  # open the linked worktree's tab
    mainWindow.tabs.setCurrentIndex(0)

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"close.+tab")
    assert os.path.exists(linked)


def testPruneWorktrees(tempDir, mainWindow):
    import shutil
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    shutil.rmtree(linked)  # stale admin entry remains
    rw.refreshRepo()
    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2  # stale row still listed

    triggerMenuAction(rw.sidebar.makeNodeMenu(header), r"prune worktrees")
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1


def testWorktreesSectionAboveStarredAndLocalBranches(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    root = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader).parent
    kinds = [n.kind for n in root.children]
    # No starred refs: Starred section is dropped, so only the Spacer separates the two headers.
    assert kinds.index(SidebarItem.LocalBranchesHeader) - kinds.index(SidebarItem.WorktreesHeader) == 2

    # With a starred ref, Starred appears BELOW Worktrees and above Local Branches.
    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")
    root = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader).parent
    kinds = [n.kind for n in root.children]
    assert kinds.index(SidebarItem.WorktreesHeader) < kinds.index(SidebarItem.StarredHeader)
    assert kinds.index(SidebarItem.StarredHeader) < kinds.index(SidebarItem.LocalBranchesHeader)


def testBranchMenuOpensExistingWorktreeInsteadOfNew(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    # no-parent is held by LinkedWT -> "Open in ... Worktree" takes over the
    # Switch-to slot; neither Switch-to nor Checkout-in-New-Worktree remains.
    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    menu = rw.sidebar.makeNodeMenu(node)
    with pytest.raises(KeyError):
        findMenuAction(menu, "checkout in new worktree")
    with pytest.raises(KeyError):
        findMenuAction(menu, "switch to")
    triggerMenuAction(menu, r"open in.+linkedwt.+worktree")
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(linked)

    # master is checked out HERE (current branch): keep upstream's disabled
    # Switch-to; no worktree entry at all (opening our own tab is pointless).
    mainWindow.tabs.setCurrentIndex(0)
    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)
    with pytest.raises(KeyError):
        findMenuAction(menu, "checkout in new worktree")
    with pytest.raises(KeyError):
        findMenuAction(menu, r"open in.+worktree")
    assert not findMenuAction(menu, "switch to").isEnabled()


def testBranchMenuKeepsNewWorktreeWhenNotCheckedOut(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    # no linked worktree; no-parent is not checked out anywhere
    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    menu = rw.sidebar.makeNodeMenu(node)
    assert findMenuAction(menu, "checkout in new worktree") is not None
    with pytest.raises(KeyError):
        findMenuAction(menu, r"open in.+worktree")


def testBranchMenuAndWorktreeRowIgnorePrunableWorktree(tempDir, mainWindow):
    import shutil
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    shutil.rmtree(linked)  # stale admin entry remains, marked prunable by git
    rw.refreshRepo()

    # Branch menu: no-parent is no longer usably checked out anywhere (its only
    # worktree's folder is gone) -> back to "checkout in new worktree", and no
    # "open in ... worktree" entry (that would just raise FileNotFoundError).
    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    menu = rw.sidebar.makeNodeMenu(node)
    assert findMenuAction(menu, "checkout in new worktree") is not None
    with pytest.raises(KeyError):
        findMenuAction(menu, r"open in.+worktree")

    # The stale Worktree sidebar row itself: "Open Worktree in New Tab" must
    # be disabled since there's no folder left to open.
    staleNode = _worktreeNodeByPath(rw, linked)
    staleMenu = rw.sidebar.makeNodeMenu(staleNode)
    openAction = findMenuAction(staleMenu, "open worktree in new tab")
    assert not openAction.isEnabled()


def testEnterStaleWorktreeRowFailsSoft(tempDir, mainWindow):
    """
    wantEnterNode (double-click/Enter) bypasses the context menu entirely, so
    the "Open Worktree in New Tab" action being disabled (asserted above)
    doesn't protect this path: RepoWidget.openWorktreeRepo must guard against
    a dead path itself instead of letting openRepo blow up with
    FileNotFoundError when the worktree's folder is gone.
    """
    import shutil
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    shutil.rmtree(linked)  # stale admin entry remains, marked prunable by git
    rw.refreshRepo()

    staleNode = _worktreeNodeByPath(rw, linked)
    tabCountBefore = mainWindow.tabs.count()

    rw.sidebar.wantEnterNode(staleNode)  # must not raise

    assert mainWindow.tabs.count() == tabCountBefore  # no new tab
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(wd)
    # Friendly status-bar toast instead of a crash dialog (RepoWidget.statusMessage
    # -> mainWindow.statusBar2, the same lightweight idiom as copyRepoPath()).
    # Path may be elided (middle-ellipsis) in the message, so just check the
    # basename survives -- ElideMiddle always keeps the tail of the string.
    assert os.path.basename(staleNode.data) in mainWindow.statusBar2.currentMessage()


def testRemoteBranchMenuOpensWorktreeOfMatchingLocalBranch(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    node = rw.sidebar.findNodeByRef("refs/remotes/origin/no-parent")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, r"open in.+linkedwt.+worktree")
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(linked)


def testNewWorktreeDialogPathLabelHasBuddy(tempDir, mainWindow):
    from gitfourchette.tasks import NewWorktree
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    assert dlg.pathLabel.buddy() is dlg.pathEdit
    assert "&" in dlg.pathLabel.text()  # mnemonic present, consumed by buddy at render time
    dlg.reject()


def testSwitchToBranchCheckedOutElsewhereOffersOpen(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    # The context menu no longer offers Switch-to for a held branch;
    # the offer is reached by attempting a switch, i.e. double-click/Enter.
    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    rw.sidebar.wantEnterNode(node)
    acceptQMessageBox(rw, r"already checked out in.+linkedwt.+open")

    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(linked)


def testSwitchToBranchCheckedOutElsewhereDeclineDoesNothing(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    rw.sidebar.wantEnterNode(node)
    rejectQMessageBox(rw, r"already checked out in.+linkedwt.+open")

    assert mainWindow.tabs.count() == 1
    assert rw.repo.head_branch_shorthand == "master"


def testMainWorktreeMarkers(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    # Tab title gets the [M] prefix (repo has a linked worktree)
    tabText = mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex())
    assert tabText.startswith("[M] ")

    # Sidebar: main worktree row -> home icon, no "(main)" suffix
    sm = rw.sidebar.sidebarModel
    wtHeader = sm.rootNode.findChild(SidebarItem.WorktreesHeader)
    mainNode = next(n for n in wtHeader.children
                    if os.path.realpath(n.data) == os.path.realpath(rw.repo.workdir))
    linkedNode = next(n for n in wtHeader.children if n is not mainNode)

    assert "(main)" not in mainNode.displayName
    mainIndex = rw.sidebar.nodeToFilterIndex(mainNode)
    linkedIndex = rw.sidebar.nodeToFilterIndex(linkedNode)
    assert mainIndex.data(SidebarModel.Role.IconKey) == "SP_DirHomeIcon"
    assert linkedIndex.data(SidebarModel.Role.IconKey) == "SP_DirIcon"


def testNoMainMarkerWithoutLinkedWorktrees(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    mainWindow.openRepo(wd)
    tabText = mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex())
    assert not tabText.startswith("[M] ")


def testMainMarkerFollowsWorktreeAddAndRemove(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert not mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex()).startswith("[M] ")

    runShellScript("git worktree add ../MarkerWT no-parent", wd)
    rw.refreshRepo()
    assert mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex()).startswith("[M] ")

    runShellScript("git worktree remove ../MarkerWT", wd)
    rw.refreshRepo()
    assert not mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex()).startswith("[M] ")


def testNewWorktreeDialogWideEnoughForPath(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    assert dlg.width() >= 640
    dlg.reject()


def testNewWorktreeTypedNameSelectsNewBranchRadio(tempDir, mainWindow):
    # Open-list bug: typing a name while "existing branch" is checked used to
    # silently DISCARD the typed name and check out the combo's branch instead.
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "TypedWT")

    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    assert not dlg.wantNewBranch()
    QTest.keyClicks(dlg.newNameEdit, "typedbranch")
    assert dlg.wantNewBranch()  # radio flipped by typing
    assert dlg.newBranchName() == "typedbranch"
    dlg.setPath(target)
    dlg.accept()

    assert "typedbranch" in rw.repo.branches.local
    from gitfourchette import worktrees
    assert any(wt.branch == "refs/heads/typedbranch" for wt in worktrees.listWorktrees(wd))


def testNewWorktreeComboPickSelectsExistingRadio(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    dlg.setNewBranch("temp", "master")
    assert dlg.wantNewBranch()
    # Simulate a user pick on the existing-branch combo (activated = user gesture)
    dlg.existingCombo.activated.emit(dlg.existingCombo.currentIndex())
    assert not dlg.wantNewBranch()  # radio flipped back
    dlg.reject()


def testRenderWorktreePathTemplate():
    from gitfourchette.worktrees import renderWorktreePathTemplate
    assert renderWorktreePathTemplate(
        "$BASE_ROOT/$REPO_NAME-$BRANCH", "/home/u/ws/repo", "feature/x") \
        == os.path.normpath("/home/u/ws/repo-feature-x")
    assert renderWorktreePathTemplate(
        "$BASE_PATH-worktrees/$BRANCH", "/home/u/ws/repo", "main") \
        == os.path.normpath("/home/u/ws/repo-worktrees/main")
    # Unknown variables stay literal; blank template yields ""
    assert "$BOGUS" in renderWorktreePathTemplate("$BASE_ROOT/$BOGUS", "/r/x", "b")
    assert renderWorktreePathTemplate("   ", "/r/x", "b") == ""


def testNewWorktreeDialogHonorsPathTemplate(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    settings.prefs.worktreePathTemplate = "$BASE_PATH-worktrees/$BRANCH"

    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    branch = dlg.existingBranch()
    expected = os.path.normpath(f"{os.path.normpath(wd)}-worktrees/{branch}")
    assert os.path.normpath(dlg.path()) == expected
    dlg.reject()


def testNewWorktreeFromRemoteBranch(tempDir, mainWindow):
    # origin/first-merge has NO local counterpart in the canned repo.
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "RemoteWT")

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/first-merge")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"new worktree here")
    dlg = findQDialog(rw, r"new worktree")
    assert dlg.wantNewBranch()
    assert dlg.newBranchName() == "first-merge"
    assert dlg.baseRef() == "origin/first-merge"
    dlg.setPath(target)
    dlg.accept()

    lb = rw.repo.branches.local["first-merge"]
    assert lb.upstream is not None
    assert lb.upstream.shorthand == "origin/first-merge"
    from gitfourchette import worktrees
    assert any(wt.branch == "refs/heads/first-merge" for wt in worktrees.listWorktrees(wd))


def testNewWorktreeFromRemoteBranchWithExistingLocal(tempDir, mainWindow):
    # local no-parent exists and is NOT checked out anywhere -> prefill existing mode.
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"new worktree here")
    dlg = findQDialog(rw, r"new worktree")
    assert not dlg.wantNewBranch()
    assert dlg.existingBranch() == "no-parent"
    dlg.reject()


def testRemoteBranchMenuHeldLocalShowsOpenInstead(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)  # holds no-parent

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/no-parent")
    menu = rw.sidebar.makeNodeMenu(node)
    assert findMenuAction(menu, r"open in.+worktree")
    with pytest.raises(KeyError):
        findMenuAction(menu, r"new worktree here")
