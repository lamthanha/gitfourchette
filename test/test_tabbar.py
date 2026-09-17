# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.forms.repostub import RepoStub
from gitfourchette.repowidget import RepoWidget
from gitfourchette.settings import TabBarClick
from .util import *


def testTabOverflow(tempDir, mainWindow):
    numRepos = 10
    tabWidget = mainWindow.tabs
    tabBar = mainWindow.tabs.tabs

    for i in range(numRepos):
        wd = unpackRepo(tempDir, renameTo=f"RepoCopy{i:04}")
        mainWindow.openRepo(wd)
        QTest.qWait(1)

        if i <= 2:  # assume no overflow when there are few repos
            assert not tabWidget.overflowGradient.isVisible()
            assert not tabWidget.overflowButton.isVisible()

    mainWindow.resize(640, 480)  # make sure it's narrow enough for overflow
    QTest.qWait(1)

    assert tabWidget.currentIndex() == numRepos - 1
    assert tabWidget.overflowGradient.isVisible()
    assert tabWidget.overflowButton.isVisible()

    # Scroll
    assert not tabBar.visibleRegion().contains(tabBar.tabRect(0))
    assert tabBar.visibleRegion().contains(tabBar.tabRect(numRepos-1))
    for _dummy in range(16):
        postMouseWheelEvent(tabBar, 120)
        QTest.qWait(0)
    assert tabBar.visibleRegion().contains(tabBar.tabRect(0))
    assert not tabBar.visibleRegion().contains(tabBar.tabRect(numRepos-1))

    # Test overflow menu
    mainWindow.tabs.overflowButton.click()
    menu: QMenu = mainWindow.findChild(QMenu, "QTW2OverflowMenu")
    triggerMenuAction(menu, "RepoCopy0002")
    menu.close()
    assert mainWindow.tabs.currentIndex() == 2


def testTabOverflowSingleTab(tempDir, mainWindow):
    from gitfourchette import settings

    wd = unpackRepo(tempDir)
    settings.history.setRepoNickname(wd, "ridiculously_long_" * 16)

    mainWindow.resize(640, 480)  # make sure it's narrow enough for overflow

    mainWindow.openRepo(wd)
    QTest.qWait(1)
    assert not mainWindow.tabs.overflowButton.isVisible()

    GFApplication.applyPrefs(autoHideTabs=True)
    QTest.qWait(1)
    assert not mainWindow.tabs.overflowButton.isVisible()


@pytest.mark.parametrize("click", ["middle", "double"])
@pytest.mark.parametrize("action", TabBarClick)
def testTabSpecialClick(tempDir, mainWindow, click, action):
    GFApplication.applyPrefs(**{f"{click}ClickTabBar": action})

    if action == "terminal":
        editorPath = getTestDataPath("editor-shim.py")
        scratchPath = f"{tempDir.name}/scratch file.txt"
        GFApplication.applyPrefs(terminal=f'"{editorPath}" "{scratchPath}" "hello world" $COMMAND')

    wd0 = unpackRepo(tempDir, renameTo="repo0")
    wd1 = unpackRepo(tempDir, renameTo="repo1")

    mainWindow._openRepo(wd0, foreground=True)  # RepoWidget
    mainWindow._openRepo(wd1, foreground=False)  # RepoStub
    assert isinstance(mainWindow.tabs.widget(0), RepoWidget)
    assert isinstance(mainWindow.tabs.widget(1), RepoStub)

    tabBar = mainWindow.tabs.tabs
    assert tabBar.count() == 2

    for tabIndex in range(tabBar.count() - 1, -1, -1):
        tab = mainWindow.tabs.widget(tabIndex)
        pos = tabBar.tabRect(tabIndex).center()
        wd = tab.workdir

        with MockDesktopServicesContext() as services:
            mouseSpecialClick(tabBar, click, pos=pos)
            QTest.qWait(0)

        assert bool(services.urls) == (action == "folder")

        if action == TabBarClick.Nothing:
            pass
        elif action == TabBarClick.Close:
            assert not any(Path(wd).samefile(tab.workdir) for tab in mainWindow.tabs.widgets())
        elif action == TabBarClick.Folder:
            assert Path(wd).samefile(services.lastUrlAsLocalFile())
        elif action == TabBarClick.Terminal:
            waitForFile(scratchPath)
            scratchText = readTextFile(scratchPath, unlink=True)
            assert "hello world" in scratchText
            assert "terminal" in scratchText
        else:
            raise NotImplementedError(f"unknown action {action}")

    assert tabBar.count() == (0 if action == "close" else 2)


# -----------------------------------------------------------------------------
# Forkette extension tests — worktree grouping in the overflow menu.

def summonOverflowMenu(mainWindow) -> QMenu:
    mainWindow.tabs.overflowButton.click()
    menu = mainWindow.findChild(QMenu, "QTW2OverflowMenu")
    assert menu is not None
    return menu


def _setUpWorktrees(tempDir, *names, repoName="BeansApp") -> tuple[str, list[str]]:
    import os
    wd = unpackRepo(tempDir, renameTo=repoName)
    parent = os.path.dirname(os.path.normpath(wd))
    paths = []
    for name in names:
        runShellScript(f"git worktree add -b wt-{name.lower()} ../{name}", wd)
        paths.append(os.path.join(parent, name))
    return wd, paths


def testTabOverflowGroupsWorktreesUnderMainWorktree(tempDir, mainWindow):
    wd, (alpha, bravo) = _setUpWorktrees(tempDir, "WtAlpha", "WtBravo")

    # Open the main worktree between its two linked worktrees: the main
    # worktree must still head the group.
    mainWindow.openRepo(alpha)
    mainWindow.openRepo(wd)
    mainWindow.openRepo(bravo)
    QTest.qWait(1)

    menu = summonOverflowMenu(mainWindow)
    try:
        # Header drops the [M] marker - the indentation conveys it now
        assert [a.text() for a in menu.actions()] == [
            "BeansApp", "    ↳ WtAlpha", "    ↳ WtBravo"]
        assert not menu.actions()[0].font().italic()

        mainWindow.tabs.setCurrentIndex(0)
        triggerMenuAction(menu, "WtBravo")
    finally:
        menu.close()

    assert mainWindow.tabs.currentIndex() == 2
    assert mainWindow.currentRepoWidget().workdir == os.path.normpath(bravo)


def testTabOverflowGhostHeaderOpensMainWorktree(tempDir, mainWindow):
    wd, (alpha,) = _setUpWorktrees(tempDir, "WtAlpha")
    other = unpackRepo(tempDir, renameTo="TypingGame")

    # Only the linked worktree is open, not the main worktree it belongs to
    mainWindow.openRepo(alpha)
    mainWindow.openRepo(other)
    QTest.qWait(1)

    menu = summonOverflowMenu(mainWindow)
    try:
        assert [a.text() for a in menu.actions()] == [
            "BeansApp", "    ↳ WtAlpha", "TypingGame"]

        ghost = findMenuAction(menu, "^BeansApp$")
        assert ghost.isEnabled(), "ghost header must stay clickable"
        assert ghost.font().italic(), "ghost header must look de-emphasized"
        ghost.trigger()
    finally:
        menu.close()
    QTest.qWait(1)

    assert mainWindow.tabs.count() == 3
    assert mainWindow.currentRepoWidget().workdir == os.path.normpath(wd)


def testTabOverflowGhostHeaderDisabledForBareRepo(tempDir, mainWindow):
    wd = unpackRepo(tempDir, renameTo="BeansApp")
    parent = os.path.dirname(os.path.normpath(wd))
    runShellScript("git clone --bare . ../Beans.git", wd)
    bare = os.path.join(parent, "Beans.git")
    runShellScript("git worktree add -b wt-bare ../WtBare master", bare)
    other = unpackRepo(tempDir, renameTo="TypingGame")

    mainWindow.openRepo(os.path.join(parent, "WtBare"))
    mainWindow.openRepo(other)
    QTest.qWait(1)

    menu = summonOverflowMenu(mainWindow)
    try:
        assert [a.text() for a in menu.actions()] == [
            "Beans.git", "    ↳ WtBare", "TypingGame"]
        # A bare repo can't be opened in a tab, so the header is inert
        assert not findMenuAction(menu, "^Beans.git$").isEnabled()
    finally:
        menu.close()
