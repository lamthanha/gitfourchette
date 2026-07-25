# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension tests — tab color dots with repo bindings.
# -----------------------------------------------------------------------------

import os

import pytest

from gitfourchette import tabcolors
from gitfourchette.application import GFApplication

from .util import *


def testRepoBindingKeyMainWorktree(tempDir):
    wd = unpackRepo(tempDir)
    assert tabcolors.repoBindingKey(wd) == os.path.realpath(wd)


def testRepoBindingKeyLinkedWorktree(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    assert tabcolors.repoBindingKey(linked) == os.path.realpath(wd)


def testRepoBindingKeySymlinkedPath(tempDir):
    wd = unpackRepo(tempDir)
    link = os.path.join(tempDir.name, "sympath")
    os.symlink(os.path.normpath(wd), link)
    assert tabcolors.repoBindingKey(link) == os.path.realpath(wd)


def testRepoBindingKeyBareRepo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git clone --bare . ../Bare.git", wd)
    bare = os.path.join(os.path.dirname(os.path.normpath(wd)), "Bare.git")
    assert tabcolors.repoBindingKey(bare) == os.path.realpath(bare)


def testResolveTabColorNamePrecedence(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    key = tabcolors.repoBindingKey(wd)
    wtKey = os.path.realpath(wd)

    # No binding, no override
    assert tabcolors.resolveTabColorName(wd) == ""

    # Binding alone
    settings.prefs.tabColorBindings[key] = "orange"
    assert tabcolors.resolveTabColorName(wd) == "orange"

    # Explicit "none" override beats binding
    settings.prefs.tabColorOverrides[wtKey] = "none"
    assert tabcolors.resolveTabColorName(wd) == ""

    # Color override beats binding
    settings.prefs.tabColorOverrides[wtKey] = "blue"
    assert tabcolors.resolveTabColorName(wd) == "blue"

    # Unknown override value degrades to binding
    settings.prefs.tabColorOverrides[wtKey] = "bogus"
    assert tabcolors.resolveTabColorName(wd) == "orange"

    # Removing the override falls back to the binding
    del settings.prefs.tabColorOverrides[wtKey]
    assert tabcolors.resolveTabColorName(wd) == "orange"

    # Unknown binding value degrades to no dot
    settings.prefs.tabColorBindings[key] = "bogus"
    assert tabcolors.resolveTabColorName(wd) == ""


def testLegacyRepoPrefsOverrideMigratesToGlobalDict(tempDir, mainWindow):
    import json

    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    # Pre-seed a legacy per-worktree override file (pre-redesign format)
    legacyFile = os.path.join(wd, ".git", f"{APP_SYSTEM_NAME}.json")
    with open(legacyFile, "w", encoding="utf-8") as f:
        json.dump({"tabColorOverride": "blue"}, f)

    rw = mainWindow.openRepo(wd)  # opening resolves colors -> triggers migration
    wtKey = os.path.realpath(wd)
    assert settings.prefs.tabColorOverrides == {wtKey: "blue"}
    assert rw.repoModel.prefs.tabColorOverride == ""
    assert _tabIconKey(mainWindow, 0) == _dotKey("blue")

    # Legacy value must not clobber an existing global entry (setdefault semantics)
    settings.prefs.tabColorOverrides[wtKey] = "teal"
    rw.repoModel.prefs.tabColorOverride = "red"
    assert tabcolors.resolveTabColorName(wd, rw.repoModel.prefs) == "teal"
    assert rw.repoModel.prefs.tabColorOverride == ""


def testTabDotIconCachedAndDistinct(mainWindow):
    assert tabcolors.tabDotIcon("red") is tabcolors.tabDotIcon("red")
    assert tabcolors.tabDotIcon("red").cacheKey() == tabcolors.tabDotIcon("red").cacheKey()
    assert tabcolors.tabDotIcon("red").cacheKey() != tabcolors.tabDotIcon("blue").cacheKey()
    for name in tabcolors.TAB_PALETTE:
        icon = tabcolors.tabDotIcon(name)
        assert not icon.isNull()
        assert not icon.pixmap(16, 16).isNull()


def testTabColorPrefFieldsDefaultsAndRoundTrip(tempDir, mainWindow):
    from gitfourchette import settings

    # Global bindings dict: default empty, survives write/load
    assert settings.prefs.tabColorBindings == {}
    settings.prefs.tabColorBindings["/some/path"] = "teal"
    settings.prefs.setDirty()
    assert settings.prefs.write(force=True)
    settings.prefs.reset()
    assert settings.prefs.tabColorBindings == {}
    settings.prefs.load()
    assert settings.prefs.tabColorBindings == {"/some/path": "teal"}

    # Per-worktree override: default empty on a real repo
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert rw.repoModel.prefs.tabColorOverride == ""


def _dotKey(colorName: str) -> int:
    return tabcolors.tabDotIcon(colorName).cacheKey()


def _tabIconKey(mainWindow, i: int):
    icon = mainWindow.tabs.tabs.tabIcon(i)
    return None if icon.isNull() else icon.cacheKey()


def _openMainAndLinkedWorktree(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    rwMain = mainWindow.openRepo(wd)
    rwChild = mainWindow.openRepo(linked)
    assert mainWindow.tabs.indexOf(rwMain) == 0
    assert mainWindow.tabs.indexOf(rwChild) == 1
    return wd, linked, rwMain, rwChild


def testSingleWorktreeRepoHasFlatColorMenu(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    mainWindow.openRepo(wd)
    menu = mainWindow.generateTabContextMenu(0)
    # Exactly one color menu, plainly titled — no worktree scope shown
    assert findMenuAction(menu, "^tab color$") is not None
    with pytest.raises(KeyError):
        findMenuAction(menu, "this worktree")
    triggerMenuAction(menu, "tab color/red")
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")


def testMultiWorktreeRepoSplitsColorMenus(tempDir, mainWindow):
    _wd, _linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    assert findMenuAction(menu, "tab color: repository") is not None
    assert findMenuAction(menu, "tab color: this worktree") is not None
    # Repository scope binds the whole repo
    triggerMenuAction(menu, "tab color: repository/orange")
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")
    # Worktree scope overrides only this worktree
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: this worktree/blue")
    assert _tabIconKey(mainWindow, 0) == _dotKey("blue")
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")


def testInheritedEntryShowsBindingColor(tempDir, mainWindow):
    _wd, _linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: repository/green")

    menu = mainWindow.generateTabContextMenu(1)
    inherited = findMenuAction(menu, r"tab color: this worktree/inherited \(green\)")
    assert inherited.isChecked()
    assert not inherited.icon().isNull()

    # Override then return to inherited
    triggerMenuAction(menu, "tab color: this worktree/red")
    menu = mainWindow.generateTabContextMenu(1)
    assert not findMenuAction(menu, r"tab color: this worktree/inherited").isChecked()
    triggerMenuAction(menu, r"tab color: this worktree/inherited")
    assert _tabIconKey(mainWindow, 1) == _dotKey("green")

    # Without a binding, the label says Inherited (No Color)
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: repository/no color")
    menu = mainWindow.generateTabContextMenu(1)
    assert findMenuAction(menu, r"tab color: this worktree/inherited \(no color\)") is not None


def testStatusRowShowsEffectiveColorAndProvenance(tempDir, mainWindow):
    _wd, _linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    # No binding, no override: no status row anywhere
    menu = mainWindow.generateTabContextMenu(0)
    with pytest.raises(KeyError):
        findMenuAction(menu, "tab color: repository/repository color")

    triggerMenuAction(menu, "tab color: repository/green")
    menu = mainWindow.generateTabContextMenu(0)
    status = findMenuAction(menu, "tab color: repository/green — repository color")
    assert not status.isEnabled()
    assert not status.icon().isNull()

    triggerMenuAction(menu, "tab color: this worktree/red")
    menu = mainWindow.generateTabContextMenu(0)
    for scope in ("repository", "this worktree"):
        status = findMenuAction(menu, f"tab color: {scope}/red — set for this worktree")
        assert not status.isEnabled()

    # "none" override reads as No color, set for this worktree
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: this worktree/no color")
    menu = mainWindow.generateTabContextMenu(0)
    assert findMenuAction(menu, "tab color: repository/no color — set for this worktree") is not None


def testBogusBindingValueChecksNoColor(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    mainWindow.openRepo(wd)
    settings.prefs.tabColorBindings[tabcolors.repoBindingKey(wd)] = "bogus"
    menu = mainWindow.generateTabContextMenu(0)
    assert findMenuAction(menu, "tab color/^no color$").isChecked()
    assert _tabIconKey(mainWindow, 0) is None


def testRepositoryMenuStaysUsableWhileOverridden(tempDir, mainWindow):
    _wd, _linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/^red$")
    assert _tabIconKey(mainWindow, 1) == _dotKey("red")

    # With the override live on this tab, repository-scope actions must stay
    # enabled and keep governing the other worktrees' tabs.
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: repository/^green$")
    assert _tabIconKey(mainWindow, 0) == _dotKey("green")   # sibling follows the binding
    assert _tabIconKey(mainWindow, 1) == _dotKey("red")     # this tab keeps its override


def testOrphanOverrideKeepsWorktreeMenuOnSingleWorktreeRepo(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    settings.prefs.tabColorOverrides[os.path.realpath(wd)] = "red"
    mainWindow.openRepo(wd)
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")
    # No linked worktrees, but the override must stay visible/clearable from the menu
    menu = mainWindow.generateTabContextMenu(0)
    assert findMenuAction(menu, "tab color: this worktree/^red$").isChecked()
    triggerMenuAction(menu, r"tab color: this worktree/inherited")
    assert _tabIconKey(mainWindow, 0) is None
    # Once cleared, the repo is back to a flat single menu
    menu = mainWindow.generateTabContextMenu(0)
    with pytest.raises(KeyError):
        findMenuAction(menu, "this worktree")


def testRepoHasLinkedWorktrees(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    assert not tabcolors.repoHasLinkedWorktrees(wd)
    runShellScript("git worktree add ../LinkedWT", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    assert tabcolors.repoHasLinkedWorktrees(wd)
    assert tabcolors.repoHasLinkedWorktrees(linked)


def testBindWholeRepoFromMainTab(tempDir, mainWindow):
    from gitfourchette import settings
    wd, _linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    assert _tabIconKey(mainWindow, 0) is None
    assert _tabIconKey(mainWindow, 1) is None

    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/orange")

    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "orange"}
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")

    # Regenerated menu shows the current binding checked, on both tabs
    for i in range(2):
        menu = mainWindow.generateTabContextMenu(i)
        assert findMenuAction(menu, "tab color: repository/^orange$").isChecked()
        assert not findMenuAction(menu, "tab color: repository/no color").isChecked()

    # No Color removes the binding and both dots
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/no color")
    assert settings.prefs.tabColorBindings == {}
    assert _tabIconKey(mainWindow, 0) is None
    assert _tabIconKey(mainWindow, 1) is None


def testBindWholeRepoFromChildWorktreeTab(tempDir, mainWindow):
    from gitfourchette import settings
    wd, _linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)

    menu = mainWindow.generateTabContextMenu(1)  # child worktree's tab
    triggerMenuAction(menu, "tab color: repository/teal")

    # Keyed to the MAIN root even when set from the child's tab
    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "teal"}
    assert _tabIconKey(mainWindow, 0) == _dotKey("teal")
    assert _tabIconKey(mainWindow, 1) == _dotKey("teal")


def testWorktreeOverride(tempDir, mainWindow):
    from gitfourchette import settings
    _wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/orange")

    # Override child to "none": child dot disappears, main keeps it
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/no color")
    assert settings.prefs.tabColorOverrides.get(os.path.realpath(linked)) == "none"
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) is None

    # Override child to blue: child blue, main orange
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/blue")
    assert settings.prefs.tabColorOverrides.get(os.path.realpath(linked)) == "blue"
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("blue")
    menu = mainWindow.generateTabContextMenu(1)
    assert findMenuAction(menu, "tab color: this worktree/^blue$").isChecked()

    # Back to Inherited: child follows the binding again
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, r"tab color: this worktree/inherited")
    assert os.path.realpath(linked) not in settings.prefs.tabColorOverrides
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")
    menu = mainWindow.generateTabContextMenu(1)
    assert findMenuAction(menu, r"tab color: this worktree/inherited").isChecked()


def testUnloadedStubTabKeepsBindingDot(tempDir, mainWindow):
    from gitfourchette.forms.repostub import RepoStub
    _wd, _linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/purple")

    mainWindow.tabs.setCurrentIndex(1)
    mainWindow.unloadOtherTabs(1)  # tab 0 becomes a RepoStub
    assert isinstance(mainWindow.tabs.widget(0), RepoStub)
    assert _tabIconKey(mainWindow, 0) == _dotKey("purple")

    # Binding and worktree-scope actions both still work on a stub tab (global storage)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: this worktree/teal")
    assert _tabIconKey(mainWindow, 0) == _dotKey("teal")
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, r"tab color: this worktree/inherited")
    menu2 = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu2, "tab color: repository/green")
    assert _tabIconKey(mainWindow, 0) == _dotKey("green")


def testTabColorPersistenceAcrossReopen(tempDir, mainWindow):
    wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/orange")
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/blue")

    mainWindow.closeTab(1)  # override already persisted to global prefs
    mainWindow.closeTab(0)
    assert mainWindow.tabs.count() == 0

    mainWindow.openRepo(wd)
    mainWindow.openRepo(linked)
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("blue")


def testUrgentIconWinsUntilTabActivated(tempDir, mainWindow):
    wd = unpackRepo(tempDir, renameTo="MainRepo")
    wd2 = unpackRepo(tempDir, renameTo="OtherRepo")
    mainWindow.openRepo(wd)
    mainWindow.openRepo(wd2)  # tab 1 is now current

    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/red")
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")

    # Urgent icon takes over the icon slot on the background tab
    mainWindow.tabs.requestAttention(0)
    urgentKey = _tabIconKey(mainWindow, 0)
    assert urgentKey is not None
    assert urgentKey != _dotKey("red")

    # A refresh must NOT stomp the urgent icon while the flag is set
    mainWindow.refreshTabColors()
    assert _tabIconKey(mainWindow, 0) == urgentKey

    # Activating the tab clears the urgent icon and restores the dot
    mainWindow.tabs.setCurrentIndex(0)
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")


def _bindOrange(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    mainWindow.openRepo(wd)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/orange")
    return wd


def testManageTabColorsOpensSettingsOnBindingsList(tempDir, mainWindow):
    _bindOrange(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/manage tab colors")
    dlg = findQDialog(mainWindow, "settings")
    listWidget: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    assert listWidget is not None
    assert listWidget.count() == 1
    assert not listWidget.item(0).icon().isNull()
    dlg.reject()


def testRemoveBindingViaSettings(tempDir, mainWindow):
    from gitfourchette import settings
    wd = _bindOrange(tempDir, mainWindow)
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")

    dlg = GFApplication.instance().openPrefsDialog("tabColorBindings")
    listWidget: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    removeButton: QPushButton = dlg.findChild(QPushButton, "tabColorBindingsRemove")
    assert listWidget.count() == 1
    assert listWidget.item(0).data(Qt.ItemDataRole.UserRole) == os.path.realpath(wd)

    listWidget.setCurrentRow(0)
    removeButton.click()
    assert listWidget.count() == 0

    # Working-copy semantics: nothing applied until OK
    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "orange"}

    dlg.accept()
    assert settings.prefs.tabColorBindings == {}
    assert _tabIconKey(mainWindow, 0) is None


def testRemoveBindingCancelKeepsBinding(tempDir, mainWindow):
    from gitfourchette import settings
    wd = _bindOrange(tempDir, mainWindow)

    dlg = GFApplication.instance().openPrefsDialog("tabColorBindings")
    listWidget: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    removeButton: QPushButton = dlg.findChild(QPushButton, "tabColorBindingsRemove")
    listWidget.setCurrentRow(0)
    removeButton.click()
    dlg.reject()

    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "orange"}
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")


def testWorktreeOverridesListedInSettings(tempDir, mainWindow):
    _wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/green")
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/no color")

    dlg = GFApplication.instance().openPrefsDialog("tabColorOverrides")
    overridesList: QListWidget = dlg.findChild(QListWidget, "tabColorOverridesList")
    bindingsList: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    assert bindingsList.count() == 1
    assert overridesList.count() == 1
    item = overridesList.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == os.path.realpath(linked)
    assert item.icon().isNull()  # "none" override: no dot icon
    dlg.reject()


def testRemoveOverrideViaSettingsRevertsToInherited(tempDir, mainWindow):
    from gitfourchette import settings
    _wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/green")
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/red")
    assert _tabIconKey(mainWindow, 1) == _dotKey("red")

    dlg = GFApplication.instance().openPrefsDialog("tabColorOverrides")
    overridesList: QListWidget = dlg.findChild(QListWidget, "tabColorOverridesList")
    removeButton: QPushButton = dlg.findChild(QPushButton, "tabColorOverridesRemove")
    assert not overridesList.item(0).icon().isNull()  # red dot shown
    overridesList.setCurrentRow(0)
    removeButton.click()
    assert overridesList.count() == 0

    # Working copy: nothing applied until OK
    assert settings.prefs.tabColorOverrides == {os.path.realpath(linked): "red"}
    dlg.accept()
    assert settings.prefs.tabColorOverrides == {}
    assert _tabIconKey(mainWindow, 1) == _dotKey("green")  # back to inherited
