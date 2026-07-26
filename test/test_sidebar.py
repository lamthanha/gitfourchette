# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import pytest
import re

from gitfourchette.nav import NavLocator
from gitfourchette.repomodel import UC_FAKEID
from gitfourchette.sidebar.sidebarmodel import SidebarItem, SidebarModel
from gitfourchette.sidebar.sidebardelegate import SidebarDelegate, SidebarClickZone, EYE_WIDTH, STAR_WIDTH, PADDING, CHILD_EXTRA_INDENT
from gitfourchette.toolbox import naturalSort
from .util import *


def _summonSearchBar(rw):
    rw.activateWindow()  # macOS offscreen compat (e.g. after a context menu)
    waitUntilTrue(rw.isActiveWindow)

    searchBar = rw.sidebar.searchBar
    assert not searchBar.isVisible()

    rw.sidebar.setFocus()
    assert rw.sidebar.hasFocus()

    QTest.keySequence(rw.window(), "Ctrl+F")
    assert searchBar.isVisible()

    return searchBar


def testCurrentBranchCannotSwitchOrMerge(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)

    assert not findMenuAction(menu, "switch to").isEnabled()
    assert not findMenuAction(menu, "merge").isEnabled()
    # assert not findMenuAction(menu, "rebase").isEnabled()


def testSidebarWithDetachedHead(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.checkout_commit(Oid(hex="7f822839a2fe9760f386cbbbcb3f92c5fe81def7"))

    rw = mainWindow.openRepo(wd)

    headNode = rw.sidebar.findNodeByRef("HEAD")
    assert headNode.kind == SidebarItem.DetachedHead
    assert headNode == rw.sidebar.findNodeByKind(SidebarItem.DetachedHead)

    toolTip = rw.sidebar.nodeToFilterIndex(headNode).data(Qt.ItemDataRole.ToolTipRole)
    assert re.search(r"detached head.+7f82283", toolTip, re.I)

    assert {'refs/heads/master', 'refs/heads/no-parent'
            } == {n.data for n in rw.sidebar.findNodesByKind(SidebarItem.LocalBranch)}


def testSidebarSelectionSync(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    # Tags are collapsed by default; expand so that jumping to a tag ref
    # further down can still be reflected as a sidebar selection (the
    # sidebar deliberately won't force-expand collapsed sections).
    sb.expand(sb.nodeToFilterIndex(sb.findNodeByKind(SidebarItem.TagsHeader)))

    rw.jump(NavLocator.inRef("HEAD"))
    assert sb.selectedIndexes()[0].data() == "master"

    rw.jump(NavLocator.inWorkdir())
    assert "workdir" in sb.selectedIndexes()[0].data().lower()

    rw.jump(NavLocator.inRef("refs/remotes/origin/first-merge"))
    assert sb.selectedIndexes()[0].data() == "first-merge"

    rw.jump(NavLocator.inRef("refs/tags/annotated_tag"))
    assert sb.selectedIndexes()[0].data() == "annotated_tag"

    # no refs point to this commit, so the sidebar shouldn't have a selection
    rw.jump(NavLocator.inCommit(Oid(hex="6db9c2ebf75590eef973081736730a9ea169a0c4")))
    assert not sb.selectedIndexes()


def testSidebarCollapsePersistent(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    sb = rw.sidebar
    sm = sb.sidebarModel
    assert sm.isAncestryChainExpanded(sb.findNodeByRef("refs/remotes/origin/master"))
    nodeToCollapse = sb.findNode(lambda n: n.data == "origin")
    indexToCollapse = sb.nodeToFilterIndex(nodeToCollapse)
    sb.collapse(indexToCollapse)
    sb.expand(indexToCollapse)  # go through both expand/collapse code paths
    sb.collapse(indexToCollapse)
    assert not sm.isAncestryChainExpanded(sb.findNodeByRef("refs/remotes/origin/master"))

    # Test that it's still hidden after a soft refresh
    mainWindow.currentRepoWidget().refreshRepo()
    assert not sm.isAncestryChainExpanded(sb.findNodeByRef("refs/remotes/origin/master"))

    # Test that it's still hidden after closing and reopening
    mainWindow.closeTab(0)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    assert not sm.isAncestryChainExpanded(sb.findNodeByRef("refs/remotes/origin/master"))


def testSidebarCollapsedHeaderShowsChildCount(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    sb = rw.sidebar

    # Tags are collapsed by default; expand so the "uncollapsed" assertion
    # below genuinely exercises the uncollapsed label for every header.
    sb.expand(sb.nodeToFilterIndex(sb.findNodeByKind(SidebarItem.TagsHeader)))

    indexes = [sb.nodeToFilterIndex(sb.findNodeByKind(kind))
               for kind in (SidebarItem.RemotesHeader,
                            SidebarItem.TagsHeader,
                            SidebarItem.StashesHeader,
                            SidebarItem.SubmodulesHeader)]

    assert [i.data() for i in indexes] == [
        "Remotes", "Tags", "Stashes", "Submodules"]

    sb.collapseAll()

    assert [i.data() for i in indexes] == [
        "Remotes (1)", "Tags (1)", "Stashes (0)", "Submodules (0)"]


def testSidebarCollapseExpandAllFolders(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("delish/drink/gazpacho")
        repo.create_branch_on_head("delish/quiche")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    sm = rw.sidebar.sidebarModel

    delish = sb.findNode(lambda n: n.data == "refs/heads/delish")
    drink = sb.findNode(lambda n: n.data == "refs/heads/delish/drink")
    quiche = sb.findNodeByRef("refs/heads/delish/quiche")
    gazpacho = sb.findNodeByRef("refs/heads/delish/drink/gazpacho")

    localBranchesNode = sb.findNodeByKind(SidebarItem.LocalBranchesHeader)
    sb.selectNode(localBranchesNode)

    def reachable():
        return {n for n in (delish, quiche, drink, gazpacho) if sm.isAncestryChainExpanded(n)}

    triggerContextMenuAction(sb.viewport(), "collapse all folders")
    assert reachable() == {delish}

    index = sb.nodeToFilterIndex(delish)
    sb.expand(index)
    assert reachable() == {delish, quiche, drink}

    triggerContextMenuAction(sb.viewport(), "expand all folders")
    assert reachable() == {delish, quiche, drink, gazpacho}


def testRefreshKeepsSidebarNonRefSelection(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    sb.setFocus()

    node = sb.findNodeByKind(SidebarItem.Remote)
    assert node.data == "origin"
    sb.selectNode(node)

    rw.refreshRepo()
    node = sb.filterIndexToNode(sb.selectedIndexes()[0])
    assert node.kind == SidebarItem.Remote
    assert node.data == "origin"


def testNewEmptyRemoteShowsUpInSidebar(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    assert 1 == sb.countNodesByKind(SidebarItem.Remote)

    rw.repo.remotes.create("toto", "https://github.com/jorio/bugdom")
    rw.refreshRepo()
    assert 2 == sb.countNodesByKind(SidebarItem.Remote)


@pytest.mark.parametrize("headerKind,leafKind", [
    (SidebarItem.LocalBranchesHeader, SidebarItem.LocalBranch),
    (SidebarItem.RemotesHeader, SidebarItem.RemoteBranch),
    (SidebarItem.TagsHeader, SidebarItem.Tag),
])
def testRefSortModes(tempDir, mainWindow, headerKind, leafKind):
    assert headerKind != leafKind

    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_tag("version2", Oid(hex='83834a7afdaa1a1260568567f6ad90020389f664'), ObjectType.COMMIT, TEST_SIGNATURE, "")
        repo.create_tag("version10", Oid(hex='6e1475206e57110fcef4b92320436c1e9872a322'), ObjectType.COMMIT, TEST_SIGNATURE, "")
        repo.create_tag("VERSION3", Oid(hex='49322bb17d3acc9146f98c97d078513228bbf3c0'), ObjectType.COMMIT, TEST_SIGNATURE, "")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    headerNode = sb.findNodeByKind(headerKind)

    def getNodeDatas():
        return [node.data for node in rw.sidebar.findNodesByKind(leafKind)]

    sortedByTimeDesc = getNodeDatas()
    sortedByTimeAsc = list(reversed(sortedByTimeDesc))
    sortedByNameAsc = sorted(getNodeDatas(), key=naturalSort)
    sortedByNameDesc = list(reversed(sortedByNameAsc))

    triggerMenuAction(sb.makeNodeMenu(headerNode), "sort.+by/newest first")
    assert getNodeDatas() == sortedByTimeDesc

    triggerMenuAction(sb.makeNodeMenu(headerNode), "sort.+by/oldest first")
    assert getNodeDatas() == sortedByTimeAsc

    triggerMenuAction(sb.makeNodeMenu(headerNode), "sort.+by/name.+a-z")
    assert getNodeDatas() == sortedByNameAsc

    # Special case for tags - test natural sorting
    if leafKind == SidebarItem.Tag:
        assert [data.removeprefix("refs/tags/") for data in getNodeDatas()
                ] == ["annotated_tag", "version2", "VERSION3", "version10"]

    triggerMenuAction(sb.makeNodeMenu(headerNode), "sort.+by/name.+z-a")
    assert getNodeDatas() == sortedByNameDesc

    # Test clearing via prefs
    pause(1)  # Let a full second roll over so that refSortResetDate (timestamp) changes
    dlg = GFApplication.instance().openPrefsDialog("refSort")
    comboBox: QComboBox = dlg.findChild(QWidget, "prefctl_refSort")
    qcbSetIndex(comboBox, "name.+a-z")
    dlg.accept()
    acceptQMessageBox(mainWindow, "take effect.+until you reload")
    del rw, sb
    rw = mainWindow.currentRepoWidget()
    assert getNodeDatas() == sortedByNameAsc


def testRefFolderSidebarDisplayNames(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        repo.create_branch_on_head("1/2A/3A")
        repo.create_branch_on_head("1/2A/3B")
        repo.create_branch_on_head("1/2B")
        repo.create_branch_on_head("4/5/6/7A")
        repo.create_branch_on_head("4/5/6/7B")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    def getRefFolderDisplayName(explicit):
        node = sb.findNode(lambda n: n.data == explicit and n.kind == SidebarItem.RefFolder)
        return node.displayName

    assert getRefFolderDisplayName("refs/heads/1") == "1"
    assert getRefFolderDisplayName("refs/heads/1/2A") == "2A"
    assert getRefFolderDisplayName("refs/heads/4/5/6") == "4/5/6"


def _eyeClickPos(node, rect):
    """
    Point inside a row's eye (Hide) click zone. On starrable rows the star now
    owns the far-right slot, so the eye sits one slot (STAR_WIDTH+PADDING) left
    of the right edge; non-starrable hideable rows keep their eye flush right.
    """
    starBand = STAR_WIDTH + PADDING if node.canBeStarred() else 0
    return QPoint(rect.right() - starBand - EYE_WIDTH // 2, rect.center().y())


@pytest.mark.parametrize("explicit,implicit", [
    ("refs/heads/1/2A/3B", []),
    ("refs/heads/1/2A", ["refs/heads/1/2A/3A", "refs/heads/1/2A/3B"]),
    ("refs/heads/1", ["refs/heads/1/2A/3A", "refs/heads/1/2A/3B", "refs/heads/1/2B"]),
    ("refs/remotes/origin/no-parent", []),
    ("origin", ["refs/remotes/origin/master", "refs/remotes/origin/no-parent", "refs/remotes/origin/first-merge"])
])
@pytest.mark.parametrize("method", ["sidebarmenu", "sidebarclick"])
def testHideNestedRefFolders(tempDir, mainWindow, explicit, implicit, method):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        repo.create_branch_on_head("1/2A/3A")
        repo.create_branch_on_head("1/2A/3B")
        repo.create_branch_on_head("1/2B")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    sm = rw.sidebar.sidebarModel

    node = sb.findNode(lambda n: n.data == explicit)

    # Trigger wantHideNode(node)
    if method == "sidebarmenu":
        triggerMenuAction(sb.makeNodeMenu(node), "hide in graph")
    elif method == "sidebarclick":
        index = sb.nodeToFilterIndex(node)
        rect = sb.visualRect(index)
        QTest.mouseClick(sb.viewport(), Qt.MouseButton.LeftButton, pos=_eyeClickPos(node, rect))
    else:
        raise NotImplementedError(f"unknown method {method}")

    for node in rw.sidebar.walk():
        index = sb.nodeToFilterIndex(node)
        tip = index.data(Qt.ItemDataRole.ToolTipRole)

        if not node.isLeafBranchKind():
            pass
        elif node.data == explicit:
            assert re.search(r"hidden", tip, re.I)
            assert sm.isExplicitlyHidden(node)
        else:
            hidden = node.data in implicit
            assert hidden == sm.isImplicitlyHidden(node)
            assert hidden ^ (not re.search(r"indirectly hidden", tip, re.I))


@pytest.mark.parametrize("explicit,implicit", [
    ("refs/heads/master", ["refs/remotes/origin/master"]),  # fork: solo shows the tracked pair
    ("refs/heads/no-parent", ["refs/remotes/origin/no-parent"]),  # fork: solo shows the tracked pair
    ("refs/heads/1", ["refs/heads/1/2A/3A", "refs/heads/1/2A/3B", "refs/heads/1/2B"]),
    ("refs/heads/1/2A", ["refs/heads/1/2A/3A", "refs/heads/1/2A/3B"]),
    ("refs/remotes/origin/no-parent", []),
    ("origin", ["refs/remotes/origin/master", "refs/remotes/origin/no-parent", "refs/remotes/origin/first-merge"])
])
@pytest.mark.parametrize("method", ["sidebarmenu", "sidebarclick"])
def testHideAllButThis(tempDir, mainWindow, explicit, implicit, method):
    leafRefs = {
        "refs/heads/master",
        "refs/heads/no-parent",
        "refs/heads/1/2B",
        "refs/heads/1/2A/3A",
        "refs/heads/1/2A/3B",
        "refs/remotes/origin/master",
        "refs/remotes/origin/no-parent",
        "refs/remotes/origin/first-merge",
    }

    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        repo.create_branch_on_head("1/2A/3A")
        repo.create_branch_on_head("1/2A/3B")
        repo.create_branch_on_head("1/2B")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    sm = rw.sidebar.sidebarModel

    node = sb.findNode(lambda n: n.data == explicit)

    # Trigger wantHideNode(node)
    if method == "sidebarmenu":
        triggerMenuAction(sb.makeNodeMenu(node), "hide all but this")
    elif method == "sidebarclick":
        index = sb.nodeToFilterIndex(node)
        rect = sb.visualRect(index)
        QTest.mouseClick(sb.viewport(), Qt.MouseButton.MiddleButton, pos=_eyeClickPos(node, rect))
    else:
        raise NotImplementedError(f"unknown method {method}")

    assert sm.isHideAllButThisMode()

    hiddenRefs = leafRefs - set(implicit)
    hiddenRefs.discard(explicit)

    for node in rw.sidebar.walk():
        index = sb.nodeToFilterIndex(node)
        tip = index.data(Qt.ItemDataRole.ToolTipRole)

        if not node.isLeafBranchKind():
            pass
        elif node.data == explicit:
            assert sm.isExplicitlyShown(node)
            assert re.search(r"hiding everything but this", tip, re.I)
        else:
            hidden = node.data in hiddenRefs
            assert hidden == sm.isImplicitlyHidden(node)
            assert hidden ^ (not re.search(r"indirectly hidden", tip, re.I))

    # Workdir row must always be visible
    uncommittedChangesIndex = rw.graphView.getFilterIndexForCommit(UC_FAKEID)
    assert uncommittedChangesIndex.isValid()
    assert uncommittedChangesIndex.row() == 0


def testSidebarToolTips(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_tag("folder/leaf", repo.head_commit_id, ObjectType.COMMIT, TEST_SIGNATURE, "hello")
        repo.create_branch_on_head("folder/leaf")
        writeFile(f"{wd}/.git/refs/remotes/origin/folder/leaf", str(repo.head_commit_id) + "\n")

    rw = mainWindow.openRepo(wd)

    def test(kind, data, *patterns):
        node = rw.sidebar.findNode(lambda n: n.kind == kind and n.data == data)
        index = rw.sidebar.nodeToFilterIndex(node)
        tip = index.data(Qt.ItemDataRole.ToolTipRole)
        for pattern in patterns:
            assert re.search(pattern, tip, re.I), f"pattern missing in tooltip: {tip}"

    test(SidebarItem.LocalBranch, "refs/heads/master",
         r"local branch", r"upstream.+origin/master", r"checked.out")

    test(SidebarItem.RemoteBranch, "refs/remotes/origin/master",
         r"origin/master", r"remote-tracking branch", r"upstream for.+checked.out.+\bmaster\b")

    test(SidebarItem.Tag, "refs/tags/annotated_tag", r"\btag\b")
    test(SidebarItem.UncommittedChanges, "", r"go to working directory.+(ctrl|⌘)")
    test(SidebarItem.UncommittedChanges, "", r"0 uncommitted changes")
    test(SidebarItem.Remote, "origin", r"https://github.com/libgit2/TestGitRepository")
    test(SidebarItem.RefFolder, "refs/heads/folder", r"local branch folder")
    test(SidebarItem.RefFolder, "refs/remotes/origin/folder", r"remote branch folder")
    test(SidebarItem.RefFolder, "refs/tags/folder", r"tag folder")


def testSidebarHeadIconAfterSwitchingBranchesPointingToSameCommit(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("other-master")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    masterIcon = sb.indexForRef("refs/heads/master").data(SidebarModel.Role.IconKey)
    otherIcon = sb.indexForRef("refs/heads/other-master").data(SidebarModel.Role.IconKey)
    assert masterIcon == "git-head"
    assert otherIcon == "git-branch"

    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/other-master")), "switch")
    acceptQMessageBox(rw, "switch")

    masterIcon = sb.indexForRef("refs/heads/master").data(SidebarModel.Role.IconKey)
    otherIcon = sb.indexForRef("refs/heads/other-master").data(SidebarModel.Role.IconKey)
    assert masterIcon == "git-branch"
    assert otherIcon == "git-head"


def testSidebarVisitRemoteWebPage(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("other-master")

    rw = mainWindow.openRepo(wd)

    with MockDesktopServicesContext() as services:
        node = rw.sidebar.findNode(lambda n: n.data == "origin" and n.kind == SidebarItem.Remote)
        menu = rw.sidebar.makeNodeMenu(node)
        triggerMenuAction(menu, "visit web page")
        assert services.urls[-1] == QUrl("https://github.com/libgit2/TestGitRepository")

        node = rw.sidebar.findNodeByRef("refs/remotes/origin/master")
        menu = rw.sidebar.makeNodeMenu(node)
        triggerMenuAction(menu, "visit web page")
        assert services.urls[-1] == QUrl("https://github.com/libgit2/TestGitRepository/tree/master")


def testSidebarAheadBehind(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        b = repo.create_branch_from_commit("ahead17", Oid(hex=("6e1475206e57110fcef4b92320436c1e9872a322")))
        b.upstream = repo.branches.remote["origin/no-parent"]

        b = repo.create_branch_from_commit("behind3", Oid(hex=("6e1475206e57110fcef4b92320436c1e9872a322")))
        b.upstream = repo.branches.remote["origin/master"]

        b = repo.create_branch_from_commit("ahead10-behind1", Oid(hex=("c070ad8c08840c8116da865b2d65593a6bb9cd2a")))
        b.upstream = repo.branches.remote["origin/no-parent"]

    rw = mainWindow.openRepo(wd)

    index = rw.sidebar.indexForRef("refs/heads/ahead17")
    tip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert re.search("17 commits ahead", tip, re.I)
    assert not re.search("commits? behind", tip, re.I)

    index = rw.sidebar.indexForRef("refs/heads/behind3")
    tip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert re.search("3 commits behind", tip, re.I)
    assert not re.search("commits? ahead", tip, re.I)

    index = rw.sidebar.indexForRef("refs/heads/ahead10-behind1")
    tip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert re.search("10 commits ahead", tip, re.I)
    assert re.search("1 commit behind", tip, re.I)

    index = rw.sidebar.indexForRef("refs/heads/no-parent")
    tip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert not re.search("commits? ahead", tip, re.I)
    assert not re.search("commit? behind", tip, re.I)
    assert re.search("up-to-date with upstream", tip, re.I)


def testSidebarMissingUpstream(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.config["branch.master.merge"] = "refs/heads/missing-upstream"

    rw = mainWindow.openRepo(wd)

    index = rw.sidebar.indexForRef("refs/heads/master")
    tip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert re.search(r"upstream missing \(origin/missing-upstream\)", tip, re.I)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)
    missingUpstreamAction = findMenuAction(menu, r"upstream.+\(missing\)/origin.missing-upstream \(missing\)")
    assert missingUpstreamAction.isChecked()

    # If we ever choose to not disable this action, the action callback should be tested as well.
    assert not missingUpstreamAction.isEnabled()


def testSidebarFilterPersistsAcrossRefresh(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("feature/login")
        repo.create_branch_on_head("bugfix/issue-123")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    searchBar = _summonSearchBar(rw)

    # Apply filter
    sb.searchBar.lineEdit.setText("feature")
    assert sb.indexForRef("refs/heads/feature/login").isValid()
    assert not sb.indexForRef("refs/heads/bugfix/issue-123").isValid()

    # Modify the repo such that the sidebar model becomes stale, then refresh
    rw.repo.create_branch_on_head("feature/logout")
    rw.refreshRepo()

    # Filter should still be applied
    assert searchBar.rawSearchTerm == "feature"
    assert rw.sidebar.indexForRef("refs/heads/feature/login").isValid()
    assert rw.sidebar.indexForRef("refs/heads/feature/logout").isValid()
    assert not rw.sidebar.indexForRef("refs/heads/bugfix/issue-123").isValid()


def testSidebarFilter(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("feature/login")
        repo.create_branch_on_head("feature/signup")
        repo.create_branch_on_head("bugfix/issue-123")
        repo.create_branch_on_head("hotfix/critical")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    searchBar = _summonSearchBar(rw)

    # Test initial state
    assert searchBar.rawSearchTerm == ""
    allBranches = sb.findNodesByKind(SidebarItem.LocalBranch)
    assert len(allBranches) >= 6  # master, no-parent, feature/*, bugfix/*, hotfix/*

    # Test filtering by "feature"
    searchBar.lineEdit.setText("feature")

    # Visible: feature branches
    assert sb.indexForRef("refs/heads/feature/login").isValid()
    assert sb.indexForRef("refs/heads/feature/signup").isValid()
    # Hidden: unrelated branches
    assert not sb.indexForRef("refs/heads/no-parent").isValid()
    assert not sb.indexForRef("refs/heads/master").isValid()

    # Test clearing filter
    searchBar.lineEdit.clear()
    assert searchBar.rawSearchTerm == ""
    # All branches visible again after clearing
    assert sb.indexForRef("refs/heads/master").isValid()
    assert sb.indexForRef("refs/heads/no-parent").isValid()

    # Test case-insensitive filtering
    searchBar.lineEdit.setText("FEATURE")
    assert sb.indexForRef("refs/heads/feature/login").isValid()
    assert sb.indexForRef("refs/heads/feature/signup").isValid()
    assert not sb.indexForRef("refs/heads/no-parent").isValid()

    # Test substring matching
    searchBar.lineEdit.setText("fix")
    assert sb.indexForRef("refs/heads/bugfix/issue-123").isValid()
    assert sb.indexForRef("refs/heads/hotfix/critical").isValid()
    # "no-parent" doesn't contain "fix", so it must be hidden
    assert not sb.indexForRef("refs/heads/no-parent").isValid()

    # Hide with keyboard shortcut
    sb.setFocus()
    QTest.keyClick(sb, Qt.Key.Key_Escape)
    assert not searchBar.isVisible()


def testSidebarFilterWithFolders(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("team/frontend/login")
        repo.create_branch_on_head("team/frontend/signup")
        repo.create_branch_on_head("team/backend/api")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    searchBar = _summonSearchBar(rw)

    # Filtering by "login" should show the matching branch and hide others
    searchBar.lineEdit.setText("login")
    assert sb.indexForRef("refs/heads/team/frontend/login").isValid()
    assert not sb.indexForRef("refs/heads/team/backend/api").isValid()
    assert not sb.indexForRef("refs/heads/team/frontend/signup").isValid()

    # Test filtering remote branches
    searchBar.lineEdit.setText("origin")
    # Remote node should be visible
    assert sb.nodeToFilterIndex(sb.findNode(lambda n: n.data == "origin")).isValid()


def testSidebarFilterWithTags(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_tag("v1.0.0", repo.head_commit_id, ObjectType.COMMIT, TEST_SIGNATURE, "")
        repo.create_tag("v2.0.0", repo.head_commit_id, ObjectType.COMMIT, TEST_SIGNATURE, "")
        repo.create_tag("release-2024", repo.head_commit_id, ObjectType.COMMIT, TEST_SIGNATURE, "")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    searchBar = _summonSearchBar(rw)

    # Filtering by "v1" should show v1.0.0 and hide the others
    searchBar.lineEdit.setText("v1")
    assert sb.indexForRef("refs/tags/v1.0.0").isValid()
    assert not sb.indexForRef("refs/tags/v2.0.0").isValid()
    assert not sb.indexForRef("refs/tags/release-2024").isValid()


def testSidebarFilterPreservesSelection(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("feature/test")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    searchBar = _summonSearchBar(rw)

    # Select a branch
    featureNode = sb.findNodeByRef("refs/heads/feature/test")
    sb.selectNode(featureNode)

    selectedBefore = sb.selectedIndexes()[0].data()
    assert "test" in selectedBefore

    # Filter that keeps the selected item visible
    searchBar.lineEdit.setText("feature")

    # The selected item should still be visible in the proxy model
    assert sb.indexForRef("refs/heads/feature/test").isValid()
    assert len(sb.selectedIndexes()) > 0


def testSidebarFilterCollapseState(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.create_branch_on_head("folder1/leaf")
        repo.create_branch_on_head("folder2/leaf")
        repo.create_branch_on_head("folder3/leaf")

    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    # Bypass isAncestryChainExpanded
    def isExpanded(ref: str) -> bool:
        i = sb.indexForRef(ref)
        assert i.isValid()

        i = i.parent()
        while i.isValid():
            if not sb.isExpanded(i):
                return False
            i = i.parent()
        return True

    # Collapse all local branch folders first
    localBranchesNode = sb.findNodeByKind(SidebarItem.LocalBranchesHeader)
    sb.selectNode(localBranchesNode)
    triggerContextMenuAction(sb.viewport(), "collapse all folders")
    assert not isExpanded("refs/heads/folder1/leaf")
    assert not isExpanded("refs/heads/folder2/leaf")
    assert not isExpanded("refs/heads/folder3/leaf")

    # Summon search bar, search for "leaf"
    searchBar = _summonSearchBar(rw)
    searchBar.lineEdit.setText("leaf")
    assert isExpanded("refs/heads/folder1/leaf")
    assert isExpanded("refs/heads/folder2/leaf")
    assert isExpanded("refs/heads/folder3/leaf")

    # Search for a term with no matches, then revert to searching for "leaf"
    searchBar.lineEdit.setText("bogusbogus")
    assert not sb.indexForRef("refs/heads/folder1/leaf").isValid()
    searchBar.lineEdit.setText("leaf")
    assert isExpanded("refs/heads/folder1/leaf")
    assert isExpanded("refs/heads/folder2/leaf")
    assert isExpanded("refs/heads/folder3/leaf")

    # Select folder2/leaf before closing search bar
    sb.selectAnyRef("refs/heads/folder2/leaf")

    # Close search bar
    searchBar.bail()

    # folder1 & folder3 must be collapsed, as they were before filtering.
    assert not isExpanded("refs/heads/folder1/leaf")
    assert not isExpanded("refs/heads/folder3/leaf")
    # folder2 was originally collapsed, but it should now be expanded because
    # we selected it before closing the search bar.
    assert isExpanded("refs/heads/folder2/leaf")


def testCopyBranchName(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"copy branch name")
    assert QApplication.clipboard().text() == "master"

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"copy branch name")
    assert QApplication.clipboard().text() == "origin/master"


def _sbExpanded(rw, node):
    return rw.sidebar.isExpanded(rw.sidebar.nodeToFilterIndex(node))


def testSidebarCollapseDefaults(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)  # origin (canned) + localfs
    runShellScript("git branch --set-upstream-to=origin/master master", wd)
    rw = mainWindow.openRepo(wd)

    origin = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "origin")
    localfs = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "localfs")
    tags = rw.sidebar.findNodeByKind(SidebarItem.TagsHeader)
    branches = rw.sidebar.findNodeByKind(SidebarItem.LocalBranchesHeader)
    remotesRoot = rw.sidebar.findNodeByKind(SidebarItem.RemotesHeader)

    assert _sbExpanded(rw, origin)          # tracked remote stays open
    assert not _sbExpanded(rw, localfs)     # other remote collapsed
    assert not _sbExpanded(rw, tags)        # tags collapsed
    assert _sbExpanded(rw, branches)        # untouched sections stay expanded
    assert _sbExpanded(rw, remotesRoot)     # remotes ROOT stays open (names visible)


def testSidebarCollapseDefaultsWithLocalUpstream(tempDir, mainWindow):
    # The checked-out branch may track a LOCAL branch (branch.<name>.remote=".").
    # pygit2 raises ValueError (not GitError) on Branch.remote_name then; this
    # must not abort opening the repo ("reference 'refs/heads/develop' is not
    # a remote branch").
    wd = unpackRepo(tempDir)
    runShellScript("git branch develop master && git branch --set-upstream-to=develop master", wd)
    rw = mainWindow.openRepo(wd)

    # No tracked remote resolvable from the upstream: fall back to "origin".
    origin = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "origin")
    tags = rw.sidebar.findNodeByKind(SidebarItem.TagsHeader)
    assert _sbExpanded(rw, origin)
    assert not _sbExpanded(rw, tags)


def testSidebarCollapseDefaultsPrimeOnlyOnce(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    runShellScript("git branch --set-upstream-to=origin/master master", wd)
    rw = mainWindow.openRepo(wd)

    # User expands everything the defaults collapsed...
    for node in [rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "localfs"),
                 rw.sidebar.findNodeByKind(SidebarItem.TagsHeader)]:
        rw.sidebar.expand(rw.sidebar.nodeToFilterIndex(node))

    mainWindow.closeTab(0)
    rw = mainWindow.openRepo(wd)

    # ...and is NOT re-collapsed on the next open
    localfs = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "localfs")
    tags = rw.sidebar.findNodeByKind(SidebarItem.TagsHeader)
    assert _sbExpanded(rw, localfs)
    assert _sbExpanded(rw, tags)


def testStarBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git branch folder/branchname master", wd)
    rw = mainWindow.openRepo(wd)

    # No Starred section while nothing is starred
    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")

    folderNode = rw.sidebar.findNodeByRef("refs/heads/folder/branchname")
    triggerMenuAction(rw.sidebar.makeNodeMenu(folderNode), r"^star branch")

    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    # "master" isn't slashed, so it stays a flat child of Starred, like a
    # top-level branch in Local Branches. "folder/branchname" IS slashed, so
    # it nests under a "folder" RefFolder, mirroring Local Branches' own
    # folder tree -- it is NOT a direct child of Starred anymore.
    assert len(starRoot.children) == 2
    assert starRoot.children[0].kind == SidebarItem.LocalBranch
    assert starRoot.children[0].data == "refs/heads/master"
    starredFolderNode = starRoot.children[1]
    assert starredFolderNode.kind == SidebarItem.RefFolder
    assert starredFolderNode.displayName == "folder"
    assert [c.data for c in starredFolderNode.children] == ["refs/heads/folder/branchname"]

    # Canonical node lookup unaffected: findNodeByRef resolves OUTSIDE Starred
    canonical = rw.sidebar.findNodeByRef("refs/heads/master")
    assert canonical.parent.kind != SidebarItem.StarredHeader

    # A starred branch nested in a folder shows only its tail ("branchname"),
    # like a branch in Local Branches -- the enclosing "folder" RefFolder
    # already disambiguates it, so the full path is no longer needed.
    folderAlias = starredFolderNode.children[0]
    assert folderAlias.data == "refs/heads/folder/branchname"
    folderAliasIndex = rw.sidebar.nodeToFilterIndex(folderAlias)
    assert folderAliasIndex.data(Qt.ItemDataRole.DisplayRole) == "branchname"

    # The alias carries a fully functional branch menu; unstar via the alias
    masterAlias = next(c for c in starRoot.children if c.data == "refs/heads/master")
    # Pin: the checked-out branch's alias inherits bold + HEAD icon ('master'
    # is checked out in the canned repo); other aliases stay non-bold.
    masterAliasIndex = rw.sidebar.nodeToFilterIndex(masterAlias)
    boldFont = masterAliasIndex.data(Qt.ItemDataRole.FontRole)
    assert boldFont is not None and boldFont.bold()
    assert masterAliasIndex.data(SidebarModel.Role.IconKey) == "git-head"
    folderFont = folderAliasIndex.data(Qt.ItemDataRole.FontRole)
    assert folderFont is None or not folderFont.bold()
    menu = rw.sidebar.makeNodeMenu(masterAlias)
    assert findMenuAction(menu, r"switch to")
    triggerMenuAction(menu, r"^unstar branch")

    # Unstar the remaining folder branch via its (freshly looked-up) canonical node
    triggerMenuAction(rw.sidebar.makeNodeMenu(rw.sidebar.findNodeByRef("refs/heads/folder/branchname")), r"^unstar branch")
    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)


def testStarRemoteBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")

    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    # A remote branch's shorthand always includes its remote name
    # ("origin/master"), so it's always slashed and nests under a folder
    # named after the remote -- mirroring how the Remotes section groups
    # branches under their remote.
    assert len(starRoot.children) == 1
    folderNode = starRoot.children[0]
    assert folderNode.kind == SidebarItem.RefFolder
    assert folderNode.displayName == "origin"

    alias = folderNode.children[0]
    assert alias.kind == SidebarItem.RemoteBranch
    assert alias.data == "refs/remotes/origin/master"

    # displayRole through the model must show just the tail ("master"), like
    # a remote branch nested under its Remote node in the Remotes section --
    # the enclosing "origin" folder already disambiguates it.
    aliasIndex = rw.sidebar.nodeToFilterIndex(alias)
    assert aliasIndex.data(Qt.ItemDataRole.DisplayRole) == "master"


def testStarredBranchPersistsAcrossReopen(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")

    mainWindow.closeTab(0)
    rw = mainWindow.openRepo(wd)
    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    assert [child.data for child in starRoot.children] == ["refs/heads/master"]


def testStarredBranchPrunedWhenBranchDeleted(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git branch doomed", wd)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/doomed")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")
    assert rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)

    node = rw.sidebar.findNodeByRef("refs/heads/doomed")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^delete")
    acceptQMessageBox(rw, r"really delete.+branch")

    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)
    assert "refs/heads/doomed" not in rw.sidebar.sidebarModel.repoModel.prefs.starredRefs


def testStarredFolderTracksMembership(tempDir, mainWindow):
    """
    Starring several branches under the same parent folder ("feat/...") must
    group them under ONE RefFolder in Starred (not one flat row apiece), and
    unstarring must shrink/remove that folder as membership drops -- exactly
    like Local Branches' own folder tree, rebuilt fresh from starredRefs on
    every model rebuild.
    """
    wd = unpackRepo(tempDir)
    runShellScript("git branch feat/a master && git branch feat/b master", wd)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    def getStarredFolder():
        starRoot = sb.findNodeByKind(SidebarItem.StarredHeader)
        return next((c for c in starRoot.children if c.kind == SidebarItem.RefFolder), None)

    # Star one branch in "feat/" -- a folder appears with one child.
    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/feat/a")), r"^star branch")
    folderNode = getStarredFolder()
    assert folderNode is not None
    assert folderNode.displayName == "feat"
    assert [c.data for c in folderNode.children] == ["refs/heads/feat/a"]

    # Star a second branch in the same folder -- one folder, two children.
    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/feat/b")), r"^star branch")
    starRoot = sb.findNodeByKind(SidebarItem.StarredHeader)
    assert len([c for c in starRoot.children if c.kind == SidebarItem.RefFolder]) == 1
    folderNode = getStarredFolder()
    assert {c.data for c in folderNode.children} == {"refs/heads/feat/a", "refs/heads/feat/b"}

    # Unstar one -- folder survives with the other child.
    aliasA = next(c for c in getStarredFolder().children if c.data == "refs/heads/feat/a")
    triggerMenuAction(sb.makeNodeMenu(aliasA), r"^unstar branch")
    folderNode = getStarredFolder()
    assert folderNode is not None
    assert [c.data for c in folderNode.children] == ["refs/heads/feat/b"]

    # Unstar the last child -- the folder (and the whole Starred section,
    # since nothing else is starred) disappears.
    aliasB = next(c for c in getStarredFolder().children if c.data == "refs/heads/feat/b")
    triggerMenuAction(sb.makeNodeMenu(aliasB), r"^unstar branch")
    assert not sb.findNodesByKind(SidebarItem.StarredHeader)


def testStarredTreeSortMatchesGlobalRefSort(tempDir, mainWindow):
    """
    Sorting within the Starred tree must follow the same global refSort
    idiom as the main sections: populateStarredRefTree reuses the exact
    RefSort branch/naturalSort logic populateRefNodeTree applies when a
    section defers to the global default, so a Starred folder isn't stuck
    with some independent ordering.
    """
    wd = unpackRepo(tempDir)
    runShellScript("git branch feat/zulu master && git branch feat/alpha master", wd)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/feat/zulu")), r"^star branch")
    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/feat/alpha")), r"^star branch")

    def getStarredFeatFolderChildren():
        starRoot = sb.findNodeByKind(SidebarItem.StarredHeader)
        folderNode = next(c for c in starRoot.children if c.kind == SidebarItem.RefFolder)
        return [c.data for c in folderNode.children]

    # Default global sort is TimeDesc. Both branches share master's commit,
    # so compare against Local Branches' own order for the same two refs
    # instead of asserting one fixed order (avoids depending on tie-breaking).
    localOrder = [n.data for n in sb.findNodesByKind(SidebarItem.LocalBranch)
                  if n.data in ("refs/heads/feat/zulu", "refs/heads/feat/alpha")]
    assert getStarredFeatFolderChildren() == localOrder

    # Switch the GLOBAL ref sort to alphabetical and force a rebuild. Starred
    # has no dedicated per-section sort override, so it must pick up the
    # global preference exactly like a main section left at its
    # UseGlobalPref default would.
    dlg = GFApplication.instance().openPrefsDialog("refSort")
    comboBox: QComboBox = dlg.findChild(QWidget, "prefctl_refSort")
    qcbSetIndex(comboBox, "name.+a-z")
    dlg.accept()
    acceptQMessageBox(mainWindow, "take effect.+until you reload")

    sb.refresh(rw.repoModel)
    assert getStarredFeatFolderChildren() == ["refs/heads/feat/alpha", "refs/heads/feat/zulu"]


def testStarredUnslashedBranchStaysFlat(tempDir, mainWindow):
    """ Starring a branch with no "/" in its name never creates a folder. """
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/master")), r"^star branch")

    starRoot = sb.findNodeByKind(SidebarItem.StarredHeader)
    assert len(starRoot.children) == 1
    assert starRoot.children[0].kind == SidebarItem.LocalBranch
    assert starRoot.children[0].data == "refs/heads/master"


def testStarredFolderCollapseIndependentOfLocalBranches(tempDir, mainWindow):
    """
    A Starred folder's collapse state must not be tied to a same-named
    folder in Local Branches: getCollapseHash() is f"{kind.name}.{data}", and
    populateStarredRefTree gives Starred folders a "starred:"-prefixed data
    precisely so the two hashes never collide.
    """
    wd = unpackRepo(tempDir)
    runShellScript("git branch folder/branchname master", wd)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    def getLocalFolder():
        return sb.findNode(lambda n: n.kind == SidebarItem.RefFolder and n.data == "refs/heads/folder")

    def getStarredFolder():
        starRoot = sb.findNodeByKind(SidebarItem.StarredHeader)
        return next(c for c in starRoot.children if c.kind == SidebarItem.RefFolder)

    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/folder/branchname")), r"^star branch")

    localFolderNode = getLocalFolder()
    starredFolderNode = getStarredFolder()
    assert starredFolderNode.data != localFolderNode.data
    assert starredFolderNode.getCollapseHash() != localFolderNode.getCollapseHash()
    assert _sbExpanded(rw, localFolderNode)
    assert _sbExpanded(rw, starredFolderNode)

    # Collapsing the Starred "folder" must not collapse Local Branches' "folder".
    sb.collapse(sb.nodeToFilterIndex(starredFolderNode))
    assert not _sbExpanded(rw, getStarredFolder())
    assert _sbExpanded(rw, getLocalFolder())

    # And the reverse: collapsing Local Branches' "folder" must not collapse
    # (or otherwise affect) Starred's, which we just re-expand to prove it.
    sb.expand(sb.nodeToFilterIndex(getStarredFolder()))
    assert _sbExpanded(rw, getStarredFolder())
    sb.collapse(sb.nodeToFilterIndex(getLocalFolder()))
    assert not _sbExpanded(rw, getLocalFolder())
    assert _sbExpanded(rw, getStarredFolder())


def testStarredFolderNotHideable(tempDir, mainWindow):
    """
    A Starred folder's `data` is a synthetic "starred:"-prefixed key, not a
    real ref prefix -- there's no refMatchingPattern() for it. It must
    therefore never expose Hide/Hide-All-But-This: feeding a bogus
    "starred:.../" pattern into RepoWidget.toggleHideRefPattern would trip
    its `assert refPattern.startswith("refs/")` (a crash dialog under normal
    runs; a silent, unmatchable show/hide pattern polluting repoModel.prefs
    under -O). Covers both the click-zone/paint path (canBeHidden()) and the
    context-menu path (which must omit the hide entries entirely).
    """
    wd = unpackRepo(tempDir)
    runShellScript("git branch folder/branchname master", wd)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    # Sanity: a REAL ref folder of the same name stays fully hideable.
    localFolderNode = sb.findNode(lambda n: n.kind == SidebarItem.RefFolder and n.data == "refs/heads/folder")
    assert localFolderNode.canBeHidden()

    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/folder/branchname")), r"^star branch")

    starRoot = sb.findNodeByKind(SidebarItem.StarredHeader)
    starredFolderNode = next(c for c in starRoot.children if c.kind == SidebarItem.RefFolder)
    assert not starredFolderNode.canBeHidden()
    assert starredFolderNode.refMatchingPattern() == ""

    # Context menu: no rename/delete (data isn't a real refs/heads/... path)
    # and no hide entries either -> empty actions -> None, same as StarredHeader.
    assert sb.makeNodeMenu(starredFolderNode) is None

    # Regression: right-click / eye-band click on a starred folder must not
    # raise, and must not toggle any hide state (getClickZone falls back to
    # Select since canBeHidden() is now False for this node).
    index = sb.nodeToFilterIndex(starredFolderNode)
    rect = sb.visualRect(index)
    QTest.mouseClick(sb.viewport(), Qt.MouseButton.LeftButton, pos=_eyeClickPos(starredFolderNode, rect))
    assert not sb.sidebarModel.isExplicitlyHidden(starredFolderNode)
    assert not sb.sidebarModel.repoModel.prefs.hidePatterns
    assert not sb.sidebarModel.repoModel.prefs.showPatterns


def testHideFromStarredAliasLeaf(tempDir, mainWindow):
    """
    Only Starred FOLDERS are inert for hiding (see
    testStarredFolderNotHideable) -- a starred alias LEAF shares kind/data
    with its canonical node, so hiding through the alias must work exactly
    like hiding through the canonical node (real refname -> real pattern).
    """
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    sm = sb.sidebarModel

    triggerMenuAction(sb.makeNodeMenu(sb.findNodeByRef("refs/heads/no-parent")), r"^star branch")

    starRoot = sb.findNodeByKind(SidebarItem.StarredHeader)
    alias = next(c for c in starRoot.children if c.data == "refs/heads/no-parent")
    assert alias.canBeHidden()
    assert alias.refMatchingPattern() == "refs/heads/no-parent"

    triggerMenuAction(sb.makeNodeMenu(alias), "hide in graph")

    # The hide actually took effect (mirrors testHideNestedRefFolders' assertions):
    # both the alias and the canonical node (same kind/data) read as hidden.
    assert sm.isExplicitlyHidden(alias)
    assert sm.isExplicitlyHidden(sb.findNodeByRef("refs/heads/no-parent"))
    aliasIndex = sb.nodeToFilterIndex(alias)
    tip = aliasIndex.data(Qt.ItemDataRole.ToolTipRole)
    assert re.search(r"hidden", tip, re.I)


def testNoExpandZoneOnChildlessNodes(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    # Canned repo has no stashes: header exists but is childless
    stashes = rw.sidebar.findNodeByKind(SidebarItem.StashesHeader)
    assert not stashes.children
    rect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(stashes))
    arrowX = rect.left() - 5  # inside the expand-arrow band (x < rect.left())
    assert SidebarDelegate.getClickZone(stashes, rect, arrowX) == SidebarClickZone.Select

    # Sections that DO have children keep their Expand zone
    branches = rw.sidebar.findNodeByKind(SidebarItem.LocalBranchesHeader)
    assert branches.children
    brect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(branches))
    assert SidebarDelegate.getClickZone(branches, brect, brect.left() - 5) == SidebarClickZone.Expand

    # Behavior level: a real click on the (now nonexistent) arrow band of a
    # childless header merely selects the row and never expands it
    # (isExpanded is NOT asserted: Qt may keep a stored expanded flag on a
    # childless item; what matters is that the click selects the row.)
    stashesIndex = rw.sidebar.nodeToFilterIndex(stashes)
    QTest.mouseClick(rw.sidebar.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(rect.left() - 5, rect.center().y()))
    assert rw.sidebar.currentIndex() == stashesIndex


def testStarClickZoneOnBranchRows(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    branch = rw.sidebar.findNodeByRef("refs/heads/master")
    rect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(branch))
    # Star owns the rightmost slot; the eye sits in the slot immediately left of it.
    starX = rect.right() - STAR_WIDTH // 2
    eyeX = rect.right() - STAR_WIDTH - PADDING - EYE_WIDTH // 2
    assert SidebarDelegate.getClickZone(branch, rect, starX) == SidebarClickZone.Star
    assert SidebarDelegate.getClickZone(branch, rect, eyeX) == SidebarClickZone.Hide
    assert SidebarDelegate.getClickZone(branch, rect, rect.center().x()) == SidebarClickZone.Select

    # Boundary: leftmost hide-zone pixel vs rightmost star-zone start
    assert SidebarDelegate.getClickZone(branch, rect, rect.right() - STAR_WIDTH - PADDING) == SidebarClickZone.Hide
    assert SidebarDelegate.getClickZone(branch, rect, rect.right() - STAR_WIDTH - PADDING + 1) == SidebarClickZone.Star
    # Boundary: Hide vs Select (left edge of the eye band)
    assert SidebarDelegate.getClickZone(branch, rect, rect.right() - STAR_WIDTH - EYE_WIDTH - PADDING) == SidebarClickZone.Select
    assert SidebarDelegate.getClickZone(branch, rect, rect.right() - STAR_WIDTH - EYE_WIDTH - PADDING + 1) == SidebarClickZone.Hide

    # Hideable-but-not-starrable rows (e.g. a Remote): the eye stays flush right
    # and no star band is introduced. The far-right slot is simply the remote's
    # own (unchanged) eye zone -- never Star -- and the leftward Hide reservation
    # that starrable rows use does not leak here.
    remote = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "origin")
    rrect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(remote))
    assert SidebarDelegate.getClickZone(remote, rrect, rrect.right() - STAR_WIDTH // 2) != SidebarClickZone.Star
    reservedX = rrect.right() - STAR_WIDTH - PADDING - EYE_WIDTH // 2
    assert SidebarDelegate.getClickZone(remote, rrect, reservedX) == SidebarClickZone.Select
    # Remote eye zone unchanged (rightmost EYE_WIDTH+PADDING band)
    assert SidebarDelegate.getClickZone(remote, rrect, rrect.right() - EYE_WIDTH - PADDING) == SidebarClickZone.Select
    assert SidebarDelegate.getClickZone(remote, rrect, rrect.right() - EYE_WIDTH - PADDING + 1) == SidebarClickZone.Hide


def testStarButtonClickTogglesStar(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    rect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(node))
    starPos = QPoint(rect.right() - STAR_WIDTH // 2, rect.center().y())
    QTest.mouseClick(rw.sidebar.viewport(), Qt.MouseButton.LeftButton, pos=starPos)
    assert "refs/heads/no-parent" in rw.sidebar.sidebarModel.repoModel.prefs.starredRefs

    # The sidebar rebuilt; unstar via the alias row's own star button
    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    alias = starRoot.children[0]
    arect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(alias))
    aliasStarPos = QPoint(arect.right() - STAR_WIDTH // 2, arect.center().y())
    QTest.mouseClick(rw.sidebar.viewport(), Qt.MouseButton.LeftButton, pos=aliasStarPos)
    assert "refs/heads/no-parent" not in rw.sidebar.sidebarModel.repoModel.prefs.starredRefs
    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)


def _recordPaintedIcons(rw, node, mouseOver, monkeypatch):
    """
    Drive the real SidebarDelegate.paint() for one row and return
    (rawRect, {iconName: paintedRect}) by recording the rect handed to each
    stockIcon's paint(). option.rect is the RAW visualRect, so the delegate
    applies its own PADDING inset -- meaning the recorded rects live in the
    same coordinate space as visualRect and are directly comparable to the
    raw-frame click zones from getClickZone.
    """
    from gitfourchette.sidebar import sidebardelegate as sd

    sb = rw.sidebar
    delegate = sb.itemDelegate()
    index = sb.nodeToFilterIndex(node)

    painted = {}

    class _RecordingIcon:
        def __init__(self, name):
            self.name = name

        def paint(self, painter, rect, *args, **kwargs):
            painted[self.name] = QRect(rect)

    monkeypatch.setattr(sd, "stockIcon", lambda name, *a, **k: _RecordingIcon(name))

    option = QStyleOptionViewItem()
    option.initFrom(sb)
    option.widget = sb
    rawRect = QRect(sb.visualRect(index))
    option.rect = QRect(rawRect)
    delegate.initStyleOption(option, index)
    option.decorationSize = QSize(16, 16)
    option.state |= QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
    if mouseOver:
        option.state |= QStyle.StateFlag.State_MouseOver
    else:
        option.state &= ~QStyle.StateFlag.State_MouseOver

    pixmap = QPixmap(rawRect.right() + 64, rawRect.bottom() + 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        delegate.paint(painter, option, index)
    finally:
        painter.end()

    return rawRect, painted


def testStarPaintDoesNotCollideWithIndicatorsOrHideZone(tempDir, mainWindow, monkeypatch):
    """
    Paint-level regression guard (records real painted rects via a
    monkeypatched stockIcon). Verifies the FIXED-slot layout: on starrable
    rows both slots are reserved whenever either band shows, so the star owns
    the far-right slot and the eye the slot immediately left of it, and neither
    ever moves horizontally.

    (a) On a starred, non-hovered row that also shows the missing-upstream
        indicator, the star rests in its fixed far-right slot and does NOT
        paint on top of the indicator.
    (b) On a hovered starrable row, the painted star lands in the raw-frame
        Star click zone and the painted eye in the Hide zone (bar the
        1px-class seam slack), eye left of star.
    (c) Stability pins: the star never moves between idle-starred and hovered
        paints of the same row; the eye never moves between idle-hidden and
        hovered paints.
    """
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        # Give 'master' a configured-but-gone upstream so its row draws the
        # git-upstream-missing indicator (same setup as testSidebarMissingUpstream).
        repo.config["branch.master.merge"] = "refs/heads/missing-upstream"
    rw = mainWindow.openRepo(wd)

    # --- (a) starred + non-hovered + missing-upstream indicator ---
    triggerMenuAction(rw.sidebar.makeNodeMenu(rw.sidebar.findNodeByRef("refs/heads/master")), r"^star branch")
    masterNode = rw.sidebar.findNodeByRef("refs/heads/master")
    rawRect, painted = _recordPaintedIcons(rw, masterNode, mouseOver=False, monkeypatch=monkeypatch)

    assert "git-upstream-missing" in painted, "missing-upstream indicator should be drawn on a non-hovered row"
    assert "star-filled" in painted, "starred row should draw the filled star"
    starRect = painted["star-filled"]
    indicatorRect = painted["git-upstream-missing"]

    # The star must not paint on top of the indicator...
    assert not starRect.intersects(indicatorRect), \
        f"star {starRect} overlaps indicator {indicatorRect}"
    # ...and it must sit flush against the row's right contents edge (rawRight - PADDING).
    contentsRight = rawRect.right() - PADDING
    assert starRect.right() >= contentsRight - 2, \
        f"star right {starRect.right()} not at contents edge {contentsRight}"

    # (c) star stability: hovering the same starred row must NOT move the star
    # (both slots stay reserved in both states).
    _, paintedMasterHover = _recordPaintedIcons(rw, masterNode, mouseOver=True, monkeypatch=monkeypatch)
    assert paintedMasterHover["star-filled"] == starRect, \
        f"star moved on hover: idle {starRect} vs hover {paintedMasterHover['star-filled']}"

    # --- (b) hovered starrable row: fixed star/eye slots, raw-frame zones ---
    hoverNode = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    rawRectB, paintedB = _recordPaintedIcons(rw, hoverNode, mouseOver=True, monkeypatch=monkeypatch)

    assert "star-outline" in paintedB or "star-filled" in paintedB, "hovered row should draw a star button"
    starB = paintedB.get("star-filled") or paintedB["star-outline"]
    eyeB = next((r for name, r in paintedB.items() if name.startswith("view-")), None)
    assert eyeB is not None, "hovered hideable row should draw an eye button"

    rawRight = rawRectB.right()
    # NEW zones: Star owns the rightmost slot, Hide the slot immediately left.
    starZoneStart = rawRight - STAR_WIDTH - PADDING              # x > this => Star
    hideZoneStart = rawRight - STAR_WIDTH - EYE_WIDTH - PADDING  # x > this => Hide

    # Star lies in the Star zone, save at most its single leftmost column (the
    # 1px-class seam that resolves to the neighbouring Hide zone).
    assert starB.left() >= starZoneStart, \
        f"star {starB} left {starB.left()} spills past Star-zone start {starZoneStart}"
    assert starB.right() > starZoneStart, f"star {starB} right not inside Star zone"
    # Eye lies in the Hide zone, save at most its single leftmost column, and
    # never bleeds into the Star zone to its right.
    assert eyeB.left() >= hideZoneStart, \
        f"eye {eyeB} left {eyeB.left()} spills past Hide-zone start {hideZoneStart}"
    assert eyeB.right() <= starZoneStart, \
        f"eye {eyeB} right {eyeB.right()} bleeds into Star zone (> {starZoneStart})"
    # Eye sits to the left of the star.
    assert eyeB.right() < starB.left(), f"eye {eyeB} overlaps star {starB}"

    # (c) eye stability: an explicitly-hidden starrable row shows its eye in the
    # fixed slot-2 position whether or not it's hovered (the star slot to its
    # right stays reserved in both states, so the eye never moves).
    triggerMenuAction(rw.sidebar.makeNodeMenu(rw.sidebar.findNodeByRef("refs/heads/no-parent")), r"hide in graph")
    hiddenNode = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    _, paintedHiddenIdle = _recordPaintedIcons(rw, hiddenNode, mouseOver=False, monkeypatch=monkeypatch)
    _, paintedHiddenHover = _recordPaintedIcons(rw, hiddenNode, mouseOver=True, monkeypatch=monkeypatch)
    eyeIdle = next((r for name, r in paintedHiddenIdle.items() if name.startswith("view-")), None)
    eyeHover = next((r for name, r in paintedHiddenHover.items() if name.startswith("view-")), None)
    assert eyeIdle is not None, "explicitly-hidden row should draw an eye when idle"
    assert eyeHover is not None
    assert eyeIdle == eyeHover, f"eye moved on hover: idle {eyeIdle} vs hover {eyeHover}"


def testSecondLevelRowsIndentDeeperThanHeaders(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar

    headerNode = sb.sidebarModel.rootNode.findChild(SidebarItem.LocalBranchesHeader)
    branchNode = sb.findNodeByRef("refs/heads/master")

    headerRect = sb.visualRect(sb.nodeToFilterIndex(headerNode))
    branchRect = sb.visualRect(sb.nodeToFilterIndex(branchNode))

    # Fork: second-level rows sit CHILD_EXTRA_INDENT px right of their headers
    # (upstream unindents them a full level, flush with the headers).
    assert branchRect.left() == headerRect.left() + CHILD_EXTRA_INDENT


def testHideLocalBranchAlsoHidesUpstreamPair(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repoModel = rw.repoModel
    assert repoModel.upstreams["master"] == "origin/master"

    rw.toggleHideRefPattern("refs/heads/master")
    assert "refs/heads/master" in repoModel.hiddenRefs
    assert "refs/remotes/origin/master" in repoModel.hiddenRefs

    # The paired upstream is IMPLICITLY hidden (indirect eye), not explicitly
    sm = rw.sidebar.sidebarModel
    remoteNode = rw.sidebar.findNodeByRef("refs/remotes/origin/master")
    assert sm.isImplicitlyHidden(remoteNode)
    assert not sm.isExplicitlyHidden(remoteNode)

    # Un-hiding the local restores the pair
    rw.toggleHideRefPattern("refs/heads/master")
    assert "refs/heads/master" not in repoModel.hiddenRefs
    assert "refs/remotes/origin/master" not in repoModel.hiddenRefs


def testHideRemoteBranchLeavesLocalAlone(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repoModel = rw.repoModel

    rw.toggleHideRefPattern("refs/remotes/origin/master")
    assert "refs/remotes/origin/master" in repoModel.hiddenRefs
    assert "refs/heads/master" not in repoModel.hiddenRefs


def testSoloLocalBranchKeepsUpstreamVisible(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repoModel = rw.repoModel

    rw.toggleHideRefPattern("refs/heads/master", allButThis=True)
    assert "refs/heads/master" not in repoModel.hiddenRefs
    assert "refs/remotes/origin/master" not in repoModel.hiddenRefs

    # Everything else stays hidden in solo mode
    others = [r for r in repoModel.refs
              if r.startswith("refs/remotes/") and r != "refs/remotes/origin/master"]
    assert others, "canned repo should have other remote refs"
    assert all(r in repoModel.hiddenRefs for r in others)


def testHideLocalWithGoneUpstreamDoesNotInjectBogusRef(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        # Point no-parent at an upstream whose remote-tracking ref doesn't exist
        repo.config["branch.no-parent.remote"] = "origin"
        repo.config["branch.no-parent.merge"] = "refs/heads/gone"

    rw = mainWindow.openRepo(wd)
    assert rw.repoModel.upstreams["no-parent"] == "origin/gone"

    # Must not crash (getHiddenTips indexes refs with every member of hiddenRefs)
    rw.toggleHideRefPattern("refs/heads/no-parent")
    assert "refs/heads/no-parent" in rw.repoModel.hiddenRefs
    assert "refs/remotes/origin/gone" not in rw.repoModel.hiddenRefs


def testHideLocalWithSharedUpstreamKeepsUpstreamVisible(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        # Second local tracking the same upstream as master
        repo.create_branch_on_head("master-twin")
        repo.config["branch.master-twin.remote"] = "origin"
        repo.config["branch.master-twin.merge"] = "refs/heads/master"

    rw = mainWindow.openRepo(wd)
    repoModel = rw.repoModel
    assert repoModel.upstreams["master"] == "origin/master"
    assert repoModel.upstreams["master-twin"] == "origin/master"

    # Hiding ONE of the two locals keeps the shared upstream visible
    rw.toggleHideRefPattern("refs/heads/master")
    assert "refs/heads/master" in repoModel.hiddenRefs
    assert "refs/remotes/origin/master" not in repoModel.hiddenRefs

    # Hiding BOTH locals finally hides the shared upstream
    rw.toggleHideRefPattern("refs/heads/master-twin")
    assert "refs/remotes/origin/master" in repoModel.hiddenRefs
