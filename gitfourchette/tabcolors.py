# -----------------------------------------------------------------------------
# Forkette extension — not part of upstream GitFourchette.
# Tab color dots: global repo bindings + per-worktree overrides.
# Resolution: override -> repo binding -> no dot.
# -----------------------------------------------------------------------------

import os
from pathlib import Path

from gitfourchette import colors
from gitfourchette import settings
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
