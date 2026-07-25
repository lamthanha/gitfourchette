# -----------------------------------------------------------------------------
# Forkette extension tests — tab color dots with repo bindings.
# -----------------------------------------------------------------------------

import os
from types import SimpleNamespace

from gitfourchette import tabcolors
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

    # No binding, no override
    assert tabcolors.resolveTabColorName(wd, None) == ""

    # Binding alone
    settings.prefs.tabColorBindings[key] = "orange"
    assert tabcolors.resolveTabColorName(wd, None) == "orange"

    # Auto override follows binding
    ns = SimpleNamespace(tabColorOverride="")
    assert tabcolors.resolveTabColorName(wd, ns) == "orange"

    # Explicit "none" override beats binding
    ns.tabColorOverride = "none"
    assert tabcolors.resolveTabColorName(wd, ns) == ""

    # Color override beats binding
    ns.tabColorOverride = "blue"
    assert tabcolors.resolveTabColorName(wd, ns) == "blue"

    # Unknown override value degrades to binding
    ns.tabColorOverride = "bogus"
    assert tabcolors.resolveTabColorName(wd, ns) == "orange"

    # Unknown binding value degrades to no dot
    settings.prefs.tabColorBindings[key] = "bogus"
    assert tabcolors.resolveTabColorName(wd, None) == ""


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
