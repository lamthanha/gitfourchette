# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension tests — Phase 3 worktree management.
# -----------------------------------------------------------------------------

import os

from gitfourchette import worktrees
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
    assert "(main)" in mainNode.displayName
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
    assert "(main)" in nodes[0].displayName


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

    # Offer to open the new worktree: decline first
    rejectQMessageBox(rw, r"open.+new tab")
    assert os.path.isdir(target)
    assert mainWindow.tabs.count() == 1
    # Sidebar refreshed with the new row
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2
    # The branch is checked out there
    from gitfourchette import worktrees
    infos = worktrees.listWorktrees(wd)
    assert infos[1].branch == "refs/heads/no-parent"


def testNewWorktreeNewBranchAndOpenTab(tempDir, mainWindow):
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

    acceptQMessageBox(rw, r"open.+new tab")
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
    rejectQMessageBox(rw, r"open.+new tab")

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
