# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — worktree grouping in the tab bar's overflow menu.
# Linked worktrees are indented under their main worktree instead of being
# listed flat. Families are keyed on tabcolors.repoBindingKey, so the menu's
# structure always agrees with the tab color dots.
# -----------------------------------------------------------------------------

import dataclasses
import enum
import os

from gitfourchette import settings
from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.tabcolors import repoBindingKey, resolveTabColorName, tabDotIcon
from gitfourchette.toolbox import compactPath, escamp, stockIcon
from gitfourchette.toolbox.qtabwidget2 import QTabWidget2

CHILD_PREFIX = "    ↳ "
"Indentation for a linked worktree listed beneath its main worktree."


class RowKind(enum.Enum):
    Flat = enum.auto()
    "Repo listed on its own (no linked worktree is open in another tab)."

    Header = enum.auto()
    "Main worktree heading its family; its own tab is open."

    GhostHeader = enum.auto()
    "Main worktree heading its family, but no tab is open for it."

    Child = enum.auto()
    "Linked worktree, indented under its family's header."


@dataclasses.dataclass(frozen=True)
class TabEntry:
    """One open tab, resolved to the repo family it belongs to."""

    index: int
    title: str
    "Tab title as displayed in the tab bar (may carry the [M] marker)."
    plainName: str
    "Repo name without the [M] marker."
    workdir: str
    familyKey: str
    "repoBindingKey: realpath of the main worktree's root."
    isMain: bool
    toolTip: str = ""
    urgent: bool = False
    "Tab is waiting for the user (see QTabWidget2.requestAttention)."


@dataclasses.dataclass(frozen=True)
class OverflowRow:
    """One row in the overflow menu."""

    kind: RowKind
    text: str
    toolTip: str = ""
    tabIndex: int = -1
    "Tab to switch to; -1 for a GhostHeader, which has no tab."
    workdir: str = ""
    "The row's repo; for a GhostHeader, the main worktree it would open."
    urgent: bool = False


def familyName(path: str) -> str:
    """Display name for a family root that has no tab of its own.

    Reads the nickname straight out of the history dict instead of going
    through getRepoNickname, which would insert an entry for a repo the user
    may never have opened.
    """
    path = os.path.normpath(path)
    entry = settings.history.repos.get(path)
    nickname = entry.get("nickname", "") if entry else ""
    return escamp(nickname or os.path.basename(path))


def groupRows(entries: list[TabEntry]) -> list[OverflowRow]:
    """Lay out tab entries as menu rows, grouping each repo's worktrees.

    Tab order is preserved: a family appears where its first member sits in
    the tab bar, and its members follow in tab order - except the main
    worktree, which is hoisted to the top of its own family.
    """
    families: dict[str, list[TabEntry]] = {}
    for entry in entries:
        families.setdefault(entry.familyKey, []).append(entry)

    rows = []

    for key, members in families.items():
        main = next((m for m in members if m.isMain), None)

        # A repo with no linked worktree open elsewhere doesn't need a family.
        if main is not None and len(members) == 1:
            rows.append(OverflowRow(RowKind.Flat, main.title, main.toolTip,
                                    main.index, main.workdir, main.urgent))
            continue

        if main is not None:
            rows.append(OverflowRow(RowKind.Header, main.plainName, main.toolTip,
                                    main.index, main.workdir, main.urgent))
        else:
            rows.append(OverflowRow(RowKind.GhostHeader, familyName(key), workdir=key))

        for member in members:
            if member is main:
                continue
            rows.append(OverflowRow(RowKind.Child, CHILD_PREFIX + member.title,
                                    member.toolTip, member.index, member.workdir,
                                    member.urgent))

    return rows


def describeTabs(mainWindow) -> list[TabEntry]:
    """Resolve every open tab to its repo family. Hits the filesystem."""
    tabBar = mainWindow.tabs.tabs
    entries = []

    for i, widget in enumerate(mainWindow.tabs.widgets()):
        title = escamp(widget.getTitle())
        toolTip = tabBar.tabToolTip(i)
        workdir = getattr(widget, "workdir", "")
        urgent = bool(widget.property(QTabWidget2.UrgentPropertyName))

        if not workdir:  # pragma: no cover - every tab is a RepoWidget/RepoStub
            entries.append(TabEntry(i, title, title, "", f"\0{i}", True, toolTip, urgent))
            continue

        familyKey = repoBindingKey(workdir)
        isMain = os.path.realpath(workdir) == familyKey
        plainName = escamp(settings.history.getRepoTabName(workdir))
        entries.append(TabEntry(i, title, plainName, workdir, familyKey, isMain, toolTip, urgent))

    return entries


def isOpenableWorkdir(path: str) -> bool:
    """True if this family root is a workdir we can open in a tab.
    False for a bare repo, or if the main worktree was moved or deleted."""
    return os.path.isdir(os.path.join(path, ".git"))


def populateOverflowMenu(menu: QMenu, mainWindow):
    """Fill the tab bar's overflow menu with grouped worktrees."""
    rows = groupRows(describeTabs(mainWindow))
    showDots = settings.prefs.tabListColorDots
    ghostFont = None

    for row in rows:
        action = QAction(row.text, menu)
        action.setToolTip(row.toolTip)

        # Same slot, same priority as the tab bar: an urgent tab is the one row
        # you need to find, so it outranks the color dot.
        if row.urgent:
            action.setIcon(stockIcon("urgent-tab"))
        elif showDots:
            colorName = resolveTabColorName(row.workdir)
            if colorName:
                action.setIcon(tabDotIcon(colorName))

        if row.kind is not RowKind.GhostHeader:
            action.triggered.connect(lambda _dummy, j=row.tabIndex: mainWindow.tabs.setCurrentIndex(j))
            menu.addAction(action)
            continue

        # Main worktree with no tab of its own. Qt can't recolor a single menu
        # row, so italics stand in for the greyed-out look.
        if ghostFont is None:
            ghostFont = QFont(menu.font())
            ghostFont.setItalic(True)
        action.setFont(ghostFont)

        path = row.workdir
        if isOpenableWorkdir(path):
            action.setToolTip(_("Open {0}", compactPath(path)))
            action.triggered.connect(lambda _dummy, p=path: mainWindow.openRepo(p))
        else:
            action.setToolTip(_("Main worktree not found: {0}", compactPath(path)))
            action.setEnabled(False)

        menu.addAction(action)


def install(mainWindow):
    """Hook the grouped menu into the tab bar's overflow button."""
    mainWindow.tabs.overflowMenuBuilder = lambda menu: populateOverflowMenu(menu, mainWindow)
