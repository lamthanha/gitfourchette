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
from gitfourchette.toolbox import stockIcon, stripAccelerators

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


def _commonGitDir(workdir: str) -> str:
    """
    Absolute path of the repo's common git dir: the main worktree's .git
    directory, or the repo dir itself for a bare repo. Best-effort for
    non-repos (returns a path whose basename is not ".git").
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
    elif not os.path.isdir(gitdir):
        return workdir  # bare repo (or not a repo at all)

    commondirFile = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondirFile):
        try:
            relCommon = Path(commondirFile).read_text("utf-8").strip()
        except OSError:
            relCommon = ""
        if relCommon:
            gitdir = os.path.realpath(os.path.join(gitdir, relCommon))

    return gitdir


def repoBindingKey(workdir: str) -> str:
    """
    Binding key for the repo containing this worktree: realpath of the main
    worktree's root (or of the repo dir itself for a bare repo).

    Parses .git gitfiles and commondir files directly (no pygit2) so it also
    works for unloaded tabs, and bind-time/resolve-time keys always agree.
    """
    gitdir = _commonGitDir(workdir)
    if os.path.basename(gitdir) == ".git":
        return os.path.realpath(os.path.dirname(gitdir))
    return gitdir


def repoHasLinkedWorktrees(workdir: str) -> bool:
    """True if the repo containing this worktree has any linked worktrees."""
    worktreesDir = os.path.join(_commonGitDir(workdir), "worktrees")
    try:
        with os.scandir(worktreesDir) as it:
            return any(it)
    except OSError:
        return False


def resolveTabColorName(workdir: str, repoPrefs=None) -> str:
    """
    Resolve the effective tab color name for a worktree, or "" for no dot.
    repoPrefs (the tab's RepoPrefs, if loaded) is only consulted to migrate a
    legacy per-worktree override into the global dict.
    """
    wtKey = os.path.realpath(workdir)

    # Legacy migration: pre-redesign builds stored the override in the
    # worktree's own gitfourchette.json.
    if repoPrefs is not None and repoPrefs.tabColorOverride:
        settings.prefs.tabColorOverrides.setdefault(wtKey, repoPrefs.tabColorOverride)
        repoPrefs.tabColorOverride = ""
        repoPrefs.setDirty()
        settings.prefs.setDirty()
        settings.prefs.write()
        repoPrefs.write()

    color, _provenance = _effectiveStatus(workdir)
    return color


def _effectiveStatus(workdir: str) -> tuple[str, str]:
    """
    (colorName, provenance) for a worktree's effective tab color.
    colorName is "" for no dot; provenance is "override", "binding", or "".
    """
    override = settings.prefs.tabColorOverrides.get(os.path.realpath(workdir), "")
    if override == OVERRIDE_NONE:
        return "", "override"
    if override in TAB_PALETTE:
        return override, "override"
    binding = settings.prefs.tabColorBindings.get(repoBindingKey(workdir), "")
    if binding in TAB_PALETTE:
        return binding, "binding"
    return "", ""


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


def _plainColorName(name: str) -> str:
    return stripAccelerators(_swatchCaptions()[name])


def _addStatusRow(menu: QMenu, workdir: str):
    """Disabled first row stating the effective color and where it comes from."""
    color, provenance = _effectiveStatus(workdir)
    if not provenance:
        return
    if provenance == "override":
        if color:
            text = _("{0} — set for this worktree", _plainColorName(color))
        else:
            text = _("No color — set for this worktree")
    else:
        text = _("{0} — repository color", _plainColorName(color))
    status = menu.addAction(text)
    if color:
        status.setIcon(tabDotIcon(color))
    status.setEnabled(False)
    menu.addSeparator()


def makeTabColorMenus(
        parentMenu: QMenu,
        workdir: str,
        repoPrefs,
        refresh: Callable[[], None],
        openSettings: Callable[[], None],
) -> list[QMenu]:
    """
    Build the tab-color submenu(s) for a repo tab's context menu.
    Single-worktree repos get one flat "Tab Color" menu (repository scope).
    Repos with linked worktrees — or with an override recorded for this
    worktree — get "Tab Color: Repository" and "Tab Color: This Worktree".
    repoPrefs (or None for an unloaded tab) only feeds legacy migration.
    """
    resolveTabColorName(workdir, repoPrefs)  # legacy-migration hook

    wtKey = os.path.realpath(workdir)
    bindingKey = repoBindingKey(workdir)
    currentBinding = settings.prefs.tabColorBindings.get(bindingKey, "")
    currentOverride = settings.prefs.tabColorOverrides.get(wtKey, "")
    splitMode = repoHasLinkedWorktrees(workdir) or bool(currentOverride)
    captions = _swatchCaptions()

    def setBinding(name: str):
        if name:
            settings.prefs.tabColorBindings[bindingKey] = name
        else:
            settings.prefs.tabColorBindings.pop(bindingKey, None)
        settings.prefs.setDirty()
        settings.prefs.write()
        refresh()

    def setOverride(value: str):
        if value:
            settings.prefs.tabColorOverrides[wtKey] = value
        else:
            settings.prefs.tabColorOverrides.pop(wtKey, None)
        settings.prefs.setDirty()
        settings.prefs.write()
        refresh()

    repoTitle = _("Tab &Color: Repository") if splitMode else _("Tab &Color")
    repoMenu = QMenu(repoTitle, parentMenu)
    repoMenu.setObjectName("MWTabColorMenu")
    _addStatusRow(repoMenu, workdir)

    for name in TAB_PALETTE:
        swatch = repoMenu.addAction(tabDotIcon(name), captions[name])
        swatch.setCheckable(True)
        swatch.setChecked(currentBinding == name)
        swatch.triggered.connect(lambda checked=False, n=name: setBinding(n))

    noColor = repoMenu.addAction(_("&No Color"))
    noColor.setCheckable(True)
    noColor.setChecked(currentBinding not in TAB_PALETTE)
    noColor.triggered.connect(lambda: setBinding(""))

    repoMenu.addSeparator()
    manage = repoMenu.addAction(_("&Manage Tab Colors…"))
    manage.triggered.connect(lambda: openSettings())

    menus = [repoMenu]
    if not splitMode:
        return menus

    wtMenu = QMenu(_("Tab Color: This &Worktree"), parentMenu)
    wtMenu.setObjectName("MWTabColorWorktreeMenu")
    _addStatusRow(wtMenu, workdir)

    for name in TAB_PALETTE:
        swatch = wtMenu.addAction(tabDotIcon(name), captions[name])
        swatch.setCheckable(True)
        swatch.setChecked(currentOverride == name)
        swatch.triggered.connect(lambda checked=False, n=name: setOverride(n))

    wtNoColor = wtMenu.addAction(_("&No Color"))
    wtNoColor.setCheckable(True)
    wtNoColor.setChecked(currentOverride == OVERRIDE_NONE)
    wtNoColor.triggered.connect(lambda: setOverride(OVERRIDE_NONE))

    if currentBinding in TAB_PALETTE:
        inheritedCaption = _("&Inherited ({0})", _plainColorName(currentBinding))
    else:
        inheritedCaption = _("&Inherited (No Color)")
    inherited = wtMenu.addAction(inheritedCaption)
    if currentBinding in TAB_PALETTE:
        inherited.setIcon(tabDotIcon(currentBinding))
    inherited.setCheckable(True)
    inherited.setChecked(currentOverride not in TAB_PALETTE and currentOverride != OVERRIDE_NONE)
    inherited.triggered.connect(lambda: setOverride(""))

    menus.append(wtMenu)
    return menus
