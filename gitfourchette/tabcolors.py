# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — not part of upstream GitFourchette.
# Tab color dots: global repo bindings + per-worktree overrides.
# Resolution: override -> repo binding -> no dot.
# -----------------------------------------------------------------------------

import os
from collections.abc import Callable
from pathlib import Path

from gitfourchette import colors, settings
from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.toolbox import stockIcon

TAB_PALETTE: dict[str, QColor] = {
    "red": colors.red,
    "orange": colors.orange,
    "yellow": colors.yellow,
    "green": colors.green,
    "teal": colors.teal,
    "blue": colors.blue,
    "purple": colors.purple,
    "gray": colors.gray,
}

OVERRIDE_NONE = "none"
"tabColorOverride value: explicitly colorless despite a repo binding."


def repoBindingKey(workdir: str) -> str:
    """
    Binding key for the repo containing this worktree: realpath of the main
    worktree's root (or of the repo dir itself for a bare repo).

    Parses .git gitfiles and commondir files directly (no pygit2) so it also
    works for unloaded tabs, and bind-time/resolve-time keys always agree.
    """
    workdir = os.path.realpath(workdir)
    gitdir = os.path.join(workdir, ".git")

    if os.path.isfile(gitdir):
        # Linked worktree (or submodule): .git is a file "gitdir: <path>"
        try:
            pointer = Path(gitdir).read_text("utf-8").strip()
        except OSError:
            return workdir
        if not pointer.startswith("gitdir:"):
            return workdir
        pointer = pointer.removeprefix("gitdir:").strip()
        gitdir = os.path.realpath(os.path.join(workdir, pointer))

    commondirFile = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondirFile):
        try:
            relCommon = Path(commondirFile).read_text("utf-8").strip()
        except OSError:
            relCommon = ""
        if relCommon:
            gitdir = os.path.realpath(os.path.join(gitdir, relCommon))

    if os.path.basename(gitdir) == ".git":
        return os.path.realpath(os.path.dirname(gitdir))
    return gitdir  # bare repo: the gitdir is the repo itself


def resolveTabColorName(workdir: str, repoPrefs) -> str:
    """
    Resolve the effective tab color name for a worktree, or "" for no dot.
    repoPrefs is a RepoPrefs (or None for an unloaded tab, where only the
    repo binding can be honored).
    """
    override = repoPrefs.tabColorOverride if repoPrefs is not None else ""
    if override == OVERRIDE_NONE:
        return ""
    if override in TAB_PALETTE:
        return override
    binding = settings.prefs.tabColorBindings.get(repoBindingKey(workdir), "")
    if binding in TAB_PALETTE:
        return binding
    return ""


def tabDotIcon(colorName: str) -> QIcon:
    """Round dot icon for a palette color. Cached by stockIcon."""
    fill = TAB_PALETTE[colorName]
    outline = fill.darker(140)
    return stockIcon("tab-dot", f"red={fill.name()} black={outline.name()}")


def _swatchCaptions() -> dict[str, str]:
    return {
        "red": _("&Red"),
        "orange": _("&Orange"),
        "yellow": _("&Yellow"),
        "green": _("&Green"),
        "teal": _("&Teal"),
        "blue": _("&Blue"),
        "purple": _("&Purple"),
        "gray": _("Gr&ay"),
    }


def makeTabColorSubmenu(
        parentMenu: QMenu,
        workdir: str,
        repoPrefs,
        refresh: Callable[[], None],
        openSettings: Callable[[], None],
) -> QMenu:
    """
    Build the "Tab Color" submenu for a repo tab's context menu.
    repoPrefs is the tab's RepoPrefs, or None for an unloaded tab (worktree
    overrides live in the repo's prefs, so that submenu is disabled then).
    """
    bindingKey = repoBindingKey(workdir)
    currentBinding = settings.prefs.tabColorBindings.get(bindingKey, "")
    currentOverride = repoPrefs.tabColorOverride if repoPrefs is not None else ""

    submenu = QMenu(_("Tab &Color"), parentMenu)
    submenu.setObjectName("MWTabColorMenu")

    def setBinding(name: str):
        if name:
            settings.prefs.tabColorBindings[bindingKey] = name
        else:
            settings.prefs.tabColorBindings.pop(bindingKey, None)
        settings.prefs.setDirty()
        settings.prefs.write()
        refresh()

    def setOverride(value: str):
        repoPrefs.tabColorOverride = value
        repoPrefs.setDirty()
        refresh()

    captions = _swatchCaptions()

    for name in TAB_PALETTE:
        swatch = submenu.addAction(tabDotIcon(name), captions[name])
        swatch.setCheckable(True)
        swatch.setChecked(currentBinding == name)
        swatch.triggered.connect(lambda checked=False, n=name: setBinding(n))

    noColor = submenu.addAction(_("&No Color"))
    noColor.setCheckable(True)
    noColor.setChecked(not currentBinding)
    noColor.triggered.connect(lambda: setBinding(""))

    submenu.addSeparator()

    worktreeMenu = submenu.addMenu(_("Only This &Worktree"))
    worktreeMenu.setObjectName("MWTabColorWorktreeMenu")
    if repoPrefs is None:
        # Disable at the action level: that's what the parent menu displays
        # and what findMenuAction/isEnabled consult.
        worktreeMenu.menuAction().setEnabled(False)
    else:
        for name in TAB_PALETTE:
            swatch = worktreeMenu.addAction(tabDotIcon(name), captions[name])
            swatch.setCheckable(True)
            swatch.setChecked(currentOverride == name)
            swatch.triggered.connect(lambda checked=False, n=name: setOverride(n))
        wtNoColor = worktreeMenu.addAction(_("&No Color"))
        wtNoColor.setCheckable(True)
        wtNoColor.setChecked(currentOverride == OVERRIDE_NONE)
        wtNoColor.triggered.connect(lambda: setOverride(OVERRIDE_NONE))
        wtAuto = worktreeMenu.addAction(_("A&uto"))  # &A is taken by Gr&ay
        wtAuto.setCheckable(True)
        wtAuto.setChecked(currentOverride not in TAB_PALETTE and currentOverride != OVERRIDE_NONE)
        wtAuto.triggered.connect(lambda: setOverride(""))

    submenu.addSeparator()
    manage = submenu.addAction(_("&Manage Tab Colors…"))
    manage.triggered.connect(lambda: openSettings())

    return submenu
