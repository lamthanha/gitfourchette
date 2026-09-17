# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension tests — worktree grouping in the tab overflow menu.
# The grouping function is pure, so these tests feed it synthetic entries
# instead of building repos on disk (see test_tabbar.py for the widget tests).
# -----------------------------------------------------------------------------

import dataclasses

from gitfourchette.taboverflow import CHILD_PREFIX, OverflowRow, RowKind, TabEntry, groupRows

MAIN = "/repos/beans-app"
OTHER = "/repos/typing-game"


def tab(index: int, name: str, family: str = MAIN, isMain: bool = False) -> TabEntry:
    workdir = family if isMain else f"/repos/{name}"
    return TabEntry(index=index, title=name, plainName=name, workdir=workdir,
                    familyKey=family, isMain=isMain)


def kinds(rows: list[OverflowRow]) -> list[RowKind]:
    return [row.kind for row in rows]


def texts(rows: list[OverflowRow]) -> list[str]:
    return [row.text for row in rows]


def testSoloMainWorktreeStaysFlat():
    rows = groupRows([tab(0, "beans-app", isMain=True)])
    assert kinds(rows) == [RowKind.Flat]
    assert texts(rows) == ["beans-app"]
    assert rows[0].tabIndex == 0


def testUnrelatedReposStayFlatInTabOrder():
    entries = [tab(0, "beans-app", isMain=True),
               tab(1, "typing-game", family=OTHER, isMain=True)]
    rows = groupRows(entries)
    assert kinds(rows) == [RowKind.Flat, RowKind.Flat]
    assert texts(rows) == ["beans-app", "typing-game"]


def testMainWorktreeHeadsItsFamily():
    entries = [tab(0, "beans-app", isMain=True), tab(1, "wt-a"), tab(2, "wt-b")]
    rows = groupRows(entries)
    assert kinds(rows) == [RowKind.Header, RowKind.Child, RowKind.Child]
    assert texts(rows) == ["beans-app", CHILD_PREFIX + "wt-a", CHILD_PREFIX + "wt-b"]
    assert [row.tabIndex for row in rows] == [0, 1, 2]


def testHeaderDropsMainWorktreeMarker():
    entry = TabEntry(index=0, title="[M] beans-app", plainName="beans-app",
                     workdir=MAIN, familyKey=MAIN, isMain=True)
    rows = groupRows([entry, tab(1, "wt-a")])
    assert rows[0].text == "beans-app"


def testMainWorktreeIsHoistedAboveEarlierChildren():
    entries = [tab(0, "wt-a"), tab(1, "beans-app", isMain=True), tab(2, "wt-b")]
    rows = groupRows(entries)
    assert kinds(rows) == [RowKind.Header, RowKind.Child, RowKind.Child]
    assert texts(rows) == ["beans-app", CHILD_PREFIX + "wt-a", CHILD_PREFIX + "wt-b"]
    assert [row.tabIndex for row in rows] == [1, 0, 2]


def testOrphanFamilyGetsGhostHeader():
    rows = groupRows([tab(0, "wt-a"), tab(1, "wt-b")])
    assert kinds(rows) == [RowKind.GhostHeader, RowKind.Child, RowKind.Child]
    assert texts(rows) == ["beans-app", CHILD_PREFIX + "wt-a", CHILD_PREFIX + "wt-b"]
    assert rows[0].tabIndex == -1
    assert rows[0].workdir == MAIN


def testLoneLinkedWorktreeStillGetsGhostHeader():
    rows = groupRows([tab(0, "wt-a")])
    assert kinds(rows) == [RowKind.GhostHeader, RowKind.Child]
    assert rows[0].workdir == MAIN


def testInterleavedFamiliesAnchorAtFirstMember():
    entries = [tab(0, "beans-app", isMain=True),
               tab(1, "typing-game", family=OTHER, isMain=True),
               tab(2, "wt-a"),
               tab(3, "tg-wt", family=OTHER)]
    rows = groupRows(entries)
    assert kinds(rows) == [RowKind.Header, RowKind.Child, RowKind.Header, RowKind.Child]
    assert texts(rows) == ["beans-app", CHILD_PREFIX + "wt-a",
                           "typing-game", CHILD_PREFIX + "tg-wt"]


def testGhostHeaderFamilyAnchorsAtFirstChild():
    entries = [tab(0, "typing-game", family=OTHER, isMain=True), tab(1, "wt-a")]
    rows = groupRows(entries)
    assert kinds(rows) == [RowKind.Flat, RowKind.GhostHeader, RowKind.Child]
    assert texts(rows) == ["typing-game", "beans-app", CHILD_PREFIX + "wt-a"]


def testEmptyInput():
    assert groupRows([]) == []


def testFlatRowKeepsMainWorktreeMarker():
    # The repo has linked worktrees, but none of them is open in a tab, so
    # there's no group to draw - and the [M] marker is the only hint left
    # that other worktrees exist.
    entry = TabEntry(index=0, title="[M] beans-app", plainName="beans-app",
                     workdir=MAIN, familyKey=MAIN, isMain=True)
    rows = groupRows([entry])
    assert kinds(rows) == [RowKind.Flat]
    assert texts(rows) == ["[M] beans-app"]


def testChildrenKeepTabOrderWhenMainComesLast():
    entries = [tab(0, "wt-a"), tab(1, "wt-b"), tab(2, "beans-app", isMain=True)]
    rows = groupRows(entries)
    assert kinds(rows) == [RowKind.Header, RowKind.Child, RowKind.Child]
    assert [row.tabIndex for row in rows] == [2, 0, 1]


def testRowsCarryWorkdirForColorLookup():
    entries = [tab(0, "wt-a"), tab(1, "beans-app", isMain=True)]
    rows = groupRows(entries)
    # The header's workdir is the main worktree; children carry their own
    assert [row.workdir for row in rows] == [MAIN, "/repos/wt-a"]


def testGhostHeaderWorkdirIsTheFamilyRoot():
    rows = groupRows([tab(0, "wt-a")])
    assert rows[0].workdir == MAIN, "no tab to read a color from - use the family root"


def testUrgentFlagReachesTheRow():
    urgent = dataclasses.replace(tab(0, "wt-a"), urgent=True)
    rows = groupRows([urgent, tab(1, "wt-b")])
    assert [row.urgent for row in rows] == [False, True, False]
