# Sidebar & Staging UX Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five Fork-parity UX features: deeper sidebar child indentation, Shift-modifier button variants (Stage All / Unstage All / Commit and Push with quiet push), Ctrl+F filtering of file lists, local-first hide-pairing, and main-worktree markers (sidebar home icon + `[M]` tab prefix).

**Architecture:** Each feature is a small, self-contained change to an existing module, except CommitAndPush which goes in a new fork task module (`gitfourchette/tasks/commitpushtasks.py`) and the file-list filter provider which goes in a new module (`gitfourchette/filelists/filelistfilter.py`). No proxy models; filtering happens inside `FileListModel`. Hide-pairing is a derived post-pass in `RepoModel.refreshHiddenRefCache` — never stored in prefs.

**Tech Stack:** Python 3, PyQt6 (tests run under PySide6 via pytest), pygit2 (reads only), real git binary via `RepoTask.flowCallGit` for mutations, pytest + pytest-xdist.

**Spec:** `docs/superpowers/specs/2026-07-26-sidebar-staging-ux-design.md` (approved 2026-07-26).

## Global Constraints

- Baseline: `fork-main` with `feat/worktree-followup` merged (commit `4868f61f` or later). Work happens on this branch, NEVER on `master`.
- Test command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` (~40–70s). 0 failed before every commit. Rerun failures in isolation before trusting them (PySide6/PyQt6 footgun).
- Targeted test runs: same command with `test/test_file.py::testName -v` and no `-n auto`.
- Every user-visible string: `_("...")` localization, typographic `…` and `’`.
- New tasks registered in BOTH `gitfourchette/tasks/__init__.py` and `TaskBook.names` in `gitfourchette/tasks/taskbook.py` (dicts alphabetized by task symbol). No `TaskBook.icons` entries.
- pygit2 is for reads only; the push in Task 4 runs the real git binary via `flowCallGit`.
- Never use `Branch.is_checked_out()` to mean "is the current branch".
- Commit trailer on every commit: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Ruff must stay clean on new/changed files (`.venv/bin/ruff check gitfourchette test` — pre-existing repo-wide I001/RUF059 noise is not yours; introduce zero NEW findings).

---

### Task 1: Deeper second-level sidebar indentation (+8px)

**Files:**
- Modify: `gitfourchette/sidebar/sidebardelegate.py:24-27` (constants), `:50-56` (`unindentRect`)
- Test: `test/test_sidebar.py`

**Interfaces:**
- Consumes: `SidebarLayout.UnindentItems` (dict of SidebarItem → −1), `Sidebar.visualRect` (already routes through `unindentRect`).
- Produces: module constant `CHILD_EXTRA_INDENT = 8` in `sidebardelegate.py`. Later tasks don't depend on it, but test code imports it.

- [ ] **Step 1: Write the failing test**

Append to `test/test_sidebar.py` (it already imports `SidebarDelegate`, `SidebarItem`, QTest helpers at the top — follow the existing import style; add `CHILD_EXTRA_INDENT` to the `sidebardelegate` import at line 13):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py::testSecondLevelRowsIndentDeeperThanHeaders -v`
Expected: FAIL — `branchRect.left() == headerRect.left()` today (assert 16 == 16 + 8 style mismatch). (If the import of `CHILD_EXTRA_INDENT` fails first, that's the expected ImportError flavor of RED; proceed.)

- [ ] **Step 3: Implement**

In `gitfourchette/sidebar/sidebardelegate.py`, add a constant next to the existing metrics (after `STAR_WIDTH = 16`):

```python
# Fork: keep child rows this many px right of their section headers.
# Upstream unindents UnindentItems a FULL level (flush with headers);
# we retreat one level minus this margin so the hierarchy stays visible.
CHILD_EXTRA_INDENT = 8
```

Change `unindentRect` to retreat by a reduced amount:

```python
    @staticmethod
    def unindentRect(item: SidebarItem, rect: QRect, indentation: int):
        if item not in SidebarLayout.UnindentItems:
            return
        unindentLevels = SidebarLayout.UnindentItems[item]
        unindentPixels = unindentLevels * (indentation - CHILD_EXTRA_INDENT)
        return rect.adjust(unindentPixels, 0, 0, 0)
```

(No other call sites change: `Sidebar.visualRect` and the delegate's `paint` both call this helper, so painting and click zones shift together.)

- [ ] **Step 4: Run the new test AND the full sidebar suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -v`
Expected: all PASS. If any pre-existing test pins absolute x coordinates that shifted by 8px, adapt ONLY the coordinate (comment `# fork: +CHILD_EXTRA_INDENT`), never the semantics. (The eye/star zone tests use `visualRect`-relative positions, so they are expected to pass unchanged.)

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/sidebar/sidebardelegate.py test/test_sidebar.py
git commit -m "feat: indent second-level sidebar rows 8px under their headers"
```

---

### Task 2: Hide-pairing — the upstream follows its local branch

**Files:**
- Modify: `gitfourchette/repomodel.py:520-538` (`refreshHiddenRefCache`)
- Test: `test/test_sidebar.py`

**Interfaces:**
- Consumes: `RepoModel.upstreams` (dict: local shorthand → upstream shorthand e.g. `"origin/master"`), `RepoModel.refs`, `RefPrefix.HEADS`/`RefPrefix.REMOTES`, `RepoWidget.toggleHideRefPattern(refPattern, allButThis=False)`.
- Produces: no new API. `hiddenRefs` now includes paired upstreams; `SidebarModel.isImplicitlyHidden` picks that up with zero UI changes.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_sidebar.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py::testHideLocalBranchAlsoHidesUpstreamPair test/test_sidebar.py::testSoloLocalBranchKeepsUpstreamVisible -v`
Expected: FAIL — `"refs/remotes/origin/master" in repoModel.hiddenRefs` is False today; solo test fails on `"refs/remotes/origin/master" not in hiddenRefs`. (`testHideRemoteBranchLeavesLocalAlone` and the gone-upstream test may already pass — they pin current behavior so the new pass can't regress it.)

- [ ] **Step 3: Implement**

In `gitfourchette/repomodel.py`, `refreshHiddenRefCache`, insert the pairing pass between the pattern-matching if/elif block and the stale-pattern check (i.e. right after the `elif hidePatterns:` block, before `if numStalePatterns > 0:`):

```python
        # Fork: local-first hide-pairing. A local branch's visibility drags its
        # upstream remote-tracking ref along, in both modes:
        # - hide mode: upstreams of hidden locals become implicitly hidden,
        #   unless a VISIBLE local also tracks the same upstream;
        # - solo mode: upstreams of visible locals are shown alongside them.
        # Hiding a remote ref directly still affects only that ref.
        # Only refs that exist may enter hiddenRefs (getHiddenTips indexes refs).
        if showPatterns or hidePatterns:
            pairedHidden = set()
            pairedVisible = set()
            for localName, upstreamShorthand in self.upstreams.items():
                if not upstreamShorthand:
                    continue
                remoteRef = RefPrefix.REMOTES + upstreamShorthand
                if remoteRef not in self.refs:
                    continue
                if RefPrefix.HEADS + localName in self.hiddenRefs:
                    pairedHidden.add(remoteRef)
                else:
                    pairedVisible.add(remoteRef)
            if showPatterns:
                self.hiddenRefs.difference_update(pairedVisible)
            else:
                self.hiddenRefs.update(pairedHidden - pairedVisible)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -v`
Expected: all PASS, including the pre-existing hide tests (`testHideNestedRefFolders`, `testHideAllButThis`, `testHideFromStarredAliasLeaf`). If a pre-existing hide test fails, STOP and reconcile: those tests define upstream semantics for refs *without* tracked pairs, which this change must not alter.

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/repomodel.py test/test_sidebar.py
git commit -m "feat: hiding a local branch implicitly hides its upstream pair"
```

---

### Task 3: File-list filtering (Ctrl+F narrows the list)

**Files:**
- Create: `gitfourchette/filelists/filelistfilter.py`
- Modify: `gitfourchette/filelists/filelistmodel.py:189-208` (`clear`, `setContents`), `gitfourchette/filelists/filelist.py:160-162` (provider wiring)
- Test: `test/test_filelist.py`

**Interfaces:**
- Consumes: `ItemViewSearchProvider` (`gitfourchette/search/itemviewsearchprovider.py`; `_buddy` is the view, `term()` returns the frozen-aware lowercase term, `_termChanged()` is the extension hook, `freeze(frozen)` is called by SearchBar's show/hideEvent), `FileList.flModel`.
- Produces: `FileListModel.setFilterTerm(term: str) -> None` (idempotent on identical term — Task 5's "visible rows" scoping relies on `flModel.deltas` being the filtered list).

- [ ] **Step 1: Write the failing test**

Append to `test/test_filelist.py` (mirror its existing imports; the helpers `unpackRepo`, `writeFile`, `qlvGetRowData`, `QTest` are already available there):

```python
def testFileListFilterNarrowsAndRestores(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/apple.txt", "a")
    writeFile(f"{wd}/banana.txt", "b")
    writeFile(f"{wd}/cherry.txt", "c")
    rw = mainWindow.openRepo(wd)
    dirty = rw.dirtyFiles

    allRows = qlvGetRowData(dirty)
    assert {"apple.txt", "banana.txt", "cherry.txt"} <= set(allRows)

    # Typing in the search bar narrows the list live (filter, not jump)
    dirty.searchBar.popUp()
    QTest.keyClicks(dirty.searchBar.lineEdit, "anan")
    assert qlvGetRowData(dirty) == ["banana.txt"]

    # Esc hides the bar AND restores the full list
    QTest.keyPress(dirty.searchBar.lineEdit, Qt.Key.Key_Escape)
    assert not dirty.searchBar.isVisibleTo(rw)
    assert set(qlvGetRowData(dirty)) == set(allRows)

    # Re-opening the bar re-applies the retained term
    dirty.searchBar.popUp()
    assert qlvGetRowData(dirty) == ["banana.txt"]


def testFileListFilterSurvivesRefresh(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/apple.txt", "a")
    writeFile(f"{wd}/banana.txt", "b")
    rw = mainWindow.openRepo(wd)
    dirty = rw.dirtyFiles

    dirty.searchBar.popUp()
    QTest.keyClicks(dirty.searchBar.lineEdit, "banana")
    assert qlvGetRowData(dirty) == ["banana.txt"]

    # A workdir refresh (setContents happens on every refresh) keeps the filter
    writeFile(f"{wd}/bananarama.txt", "b2")
    rw.refreshRepo()
    assert set(qlvGetRowData(dirty)) == {"banana.txt", "bananarama.txt"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_filelist.py::testFileListFilterNarrowsAndRestores -v`
Expected: FAIL — today typing only highlights; `qlvGetRowData(dirty)` still returns all three rows.

- [ ] **Step 3: Implement the model-side filter**

In `gitfourchette/filelists/filelistmodel.py`:

In `clear()` (line 189), add the backing-store reset — the method becomes:

```python
    def clear(self):
        self.deltas = []
        self.fileRows = {}
        self._allDeltas = []
        self._filterTerm = ""
        self.highlightedCounterpartRow = -1
        self.navLocator = NavLocator.Empty
        self.modelReset.emit()
```

(`clear()` is called from `__init__`'s path already — verify `_allDeltas`/`_filterTerm` exist before first `setContents` by running the test file; if `clear()` is not called from the constructor, initialize both attributes in `__init__` too.)

Replace `setContents` (line 196) and add the two new methods:

```python
    def setContents(self, deltas: Iterable[GitDelta]):
        self._allDeltas = sorted(deltas, key=lambda d: naturalSort(d.new.path))
        self._rebuildFilteredRows()

    def setFilterTerm(self, term: str):
        # Fork: Fork.dev-style file list filtering (driven by the search bar).
        term = term.strip().lower()
        if term == self._filterTerm:
            return  # also breaks the reset->reevaluate->setTerm recursion
        self._filterTerm = term
        self._rebuildFilteredRows()

    def _rebuildFilteredRows(self):
        self.beginResetModel()
        self.deltas = []
        self.fileRows = {}
        for delta in self._allDeltas:
            if self._filterTerm and self._filterTerm not in delta.new.path.lower():
                continue
            self.fileRows[delta.new.path] = len(self.deltas)
            self.deltas.append(delta)
        self.endResetModel()
```

- [ ] **Step 4: Implement the filter provider (new module)**

Create `gitfourchette/filelists/filelistfilter.py`:

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""
Fork: search provider that turns the file lists' Ctrl+F bar into a FILTER
(Fork.dev-style): typing narrows the list to matching paths instead of merely
jumping to matches. Consistent with the sidebar, whose Ctrl+F also filters.
"""

from __future__ import annotations

import typing

from gitfourchette.search.itemviewsearchprovider import ItemViewSearchProvider

if typing.TYPE_CHECKING:
    from gitfourchette.filelists.filelist import FileList


class FileListFilter(ItemViewSearchProvider):
    @property
    def fileList(self) -> FileList:
        from gitfourchette.filelists.filelist import FileList
        assert isinstance(self._buddy, FileList)
        return self._buddy

    def _termChanged(self):
        self.fileList.flModel.setFilterTerm(self.term())

    def freeze(self, frozen: bool):
        # SearchBar freezes the provider when the bar hides (Esc) and thaws it
        # on show. A hidden bar must always mean "no filter"; on re-show, the
        # bar's showEvent reevaluates the term and the filter reapplies.
        super().freeze(frozen)
        if frozen:
            self.fileList.flModel.setFilterTerm("")
```

In `gitfourchette/filelists/filelist.py`, swap the provider (line ~160):

```python
        searchProvider = FileListFilter(self)
        searchProvider.dataRole = FileListModel.Role.FilePath
```

and add the import near the other `gitfourchette.filelists` imports:

```python
from gitfourchette.filelists.filelistfilter import FileListFilter
```

(The old `ItemViewSearchProvider` import in `filelist.py` becomes unused if nothing else references it — remove it in that case; ruff will tell you.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_filelist.py test/test_diff.py test/test_navigation.py -v`
Expected: all PASS. The navigation/diff suites exercise `setContents` and selection restoration heavily — they guard the model rework.

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/filelists/filelistfilter.py gitfourchette/filelists/filelistmodel.py gitfourchette/filelists/filelist.py test/test_filelist.py
git commit -m "feat: Ctrl+F filters file lists (Fork-style) instead of jump-search"
```

---

### Task 4: CommitAndPush task (quiet push, dialog fallback)

**Files:**
- Create: `gitfourchette/tasks/commitpushtasks.py`
- Modify: `gitfourchette/tasks/__init__.py` (import, alphabetized), `gitfourchette/tasks/taskbook.py` (`TaskBook.names`, alphabetized)
- Create: `test/test_shiftbuttons.py`

**Interfaces:**
- Consumes: `NewCommit` (raises `AbortTask` when the commit dialog is rejected — verified at `committasks.py:110`), `PushBranch` (dialog flow), `split_remote_branch_shorthand` (porcelain), `RepoTask.flowCallGit`, `TaskEffects`, `TaskPrereqs`.
- Produces: `class CommitAndPush(RepoTask)` with `flow(self)` (no arguments), importable as `from gitfourchette.tasks import CommitAndPush`. Task 5's commit-button routing invokes it via `CommitAndPush.invoke(self)`.

- [ ] **Step 1: Write the failing tests**

Create `test/test_shiftbuttons.py` (header mirrors `test/test_tasks_commit.py`'s import style):

```python
# -----------------------------------------------------------------------------
# Fork: tests for Shift-modifier staging buttons and the CommitAndPush task.
# -----------------------------------------------------------------------------

from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.pushdialog import PushDialog
from gitfourchette.tasks import CommitAndPush

from .util import *


def _stageFirstDirtyFile(rw):
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)


def testCommitAndPushQuietToUpstream(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)  # retargets upstreams to localfs/*
    writeFile(f"{wd}/pushme.txt", "and push me now")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    oldRemoteTip = rw.repo.branches.remote["localfs/master"].target

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "commit-and-push me")
    dialog.acceptButton.click()

    localTip = rw.repo.branches.local["master"].target
    assert localTip != oldRemoteTip
    assert rw.repo.branches.remote["localfs/master"].target == localTip


def testCommitAndPushNoUpstreamFallsBackToPushDialog(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    runShellScript("git switch -c standalone", wd)  # branch with no upstream
    writeFile(f"{wd}/pushme.txt", "no upstream here")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "commit on standalone")
    dialog.acceptButton.click()

    pushDialog = findQDialog(rw, "push.+branch")
    assert isinstance(pushDialog, PushDialog)
    pushDialog.reject()


def testCommitAndPushCancelledCommitPushesNothing(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    writeFile(f"{wd}/pushme.txt", "never committed")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    oldLocalTip = rw.repo.branches.local["master"].target
    oldRemoteTip = rw.repo.branches.remote["localfs/master"].target

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    dialog.reject()

    assert rw.repo.branches.local["master"].target == oldLocalTip
    assert rw.repo.branches.remote["localfs/master"].target == oldRemoteTip
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_shiftbuttons.py -v`
Expected: FAIL at collection — `ImportError: cannot import name 'CommitAndPush'`.

- [ ] **Step 3: Implement the task**

Create `gitfourchette/tasks/commitpushtasks.py`:

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""
Fork: Commit-and-Push — Fork.dev-style Shift+Commit.

Runs NewCommit (cancelling its dialog aborts everything), then pushes the
checked-out branch to its upstream QUIETLY (status-bar indicator only, like
quiet fetch). If the branch has no upstream, falls back to the Push dialog.
"""

from gitfourchette.localization import *
from gitfourchette.porcelain import *
from gitfourchette.tasks.committasks import NewCommit
from gitfourchette.tasks.nettasks import PushBranch
from gitfourchette.tasks.repotask import RepoTask, TaskEffects, TaskPrereqs
from gitfourchette.toolbox import *


class CommitAndPush(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoDetached

    def broadcastProcesses(self) -> bool:
        # Fork-style quiet push: no modal ProcessDialog.
        return False

    def flow(self):
        yield from self.flowSubtask(NewCommit)

        branchName = self.repo.head_branch_shorthand
        branch = self.repo.branches.local[branchName]
        upstream = branch.upstream
        if upstream is None:
            # No upstream to push to quietly: let the user pick one.
            yield from self.flowSubtask(PushBranch, branchName)
            return

        remoteName, remoteBranchName = split_remote_branch_shorthand(upstream.shorthand)
        self.epilog.effects |= TaskEffects.Refs
        yield from self.flowCallGit(
            "push",
            "--porcelain",
            "--progress",
            remoteName,
            f"refs/heads/{branchName}:refs/heads/{remoteBranchName}")
        self.epilog.status = _("Pushed {0} to {1}.", tquo(branchName), tquo(upstream.shorthand))
```

(If `split_remote_branch_shorthand` is not exported by `gitfourchette.porcelain`'s star-import, import it the way `nettasks.py` does — check that file's import block and copy the exact form.)

- [ ] **Step 4: Register the task (both places)**

In `gitfourchette/tasks/__init__.py`, add alphabetically among the module imports:

```python
from gitfourchette.tasks.commitpushtasks import CommitAndPush
```

(If the file maintains an `__all__` list, add `"CommitAndPush"` there alphabetically too.)

In `gitfourchette/tasks/taskbook.py`, add to `TaskBook.names` in alphabetical symbol order:

```python
            tasks.CommitAndPush: _("Commit and push"),
```

No `TaskBook.icons` entry, no shortcut.

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_shiftbuttons.py test/test_repotask.py -v`
Expected: all PASS. (`test_repotask.py` contains the TaskBook registration sanity checks — it fails loudly if a task is missing from `TaskBook.names`.)

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/tasks/commitpushtasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py test/test_shiftbuttons.py
git commit -m "feat: CommitAndPush task (quiet push to upstream, Push dialog fallback)"
```

---

### Task 5: Shift-modifier button swap in DiffArea

**Files:**
- Modify: `gitfourchette/diffarea.py` (imports line 26, `__init__`, `_makeDirtyContainer`, `_makeStageContainer`, new methods), `gitfourchette/filelists/dirtyfiles.py:132-134`, `gitfourchette/filelists/stagedfiles.py:79-81`
- Test: `test/test_shiftbuttons.py`

**Interfaces:**
- Consumes: `CommitAndPush` (Task 4), `FileListModel.deltas` as the visible (filtered) row list (Task 3), `StageFiles`/`UnstageFiles` task invocation pattern (`StageFiles.invoke(self, deltas)`), `GFApplication.instance()`.
- Produces: `DirtyFiles.stageAll()`, `StagedFiles.unstageAll()`, `DiffArea.setShiftButtonsEngaged(engaged: bool)` (test hook — tests drive it via real Shift key events, not by calling it).

- [ ] **Step 1: Write the failing tests**

Append to `test/test_shiftbuttons.py`:

```python
def testShiftSwapsStagingButtonLabels(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/hello.txt", "hello")
    rw = mainWindow.openRepo(wd)
    area = rw.diffArea

    assert area.stageButton.text() == "Stage"
    assert area.unstageButton.text() == "Unstage"
    assert area.commitButton.text() == "Commit"

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    assert area.stageButton.text() == "Stage All"
    assert area.unstageButton.text() == "Unstage All"
    assert area.commitButton.text() == "Commit and Push"
    # All-variants enable off the LIST, not the selection
    assert area.stageButton.isEnabled()

    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)
    assert area.stageButton.text() == "Stage"
    assert area.commitButton.text() == "Commit"


def testShiftStageAllAndUnstageAll(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/apple.txt", "a")
    writeFile(f"{wd}/banana.txt", "b")
    writeFile(f"{wd}/cherry.txt", "c")
    rw = mainWindow.openRepo(wd)
    area = rw.diffArea

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    area.stageButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)
    assert {"apple.txt", "banana.txt", "cherry.txt"} <= set(qlvGetRowData(rw.stagedFiles))
    assert qlvGetRowData(rw.dirtyFiles) == []

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    area.unstageButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)
    assert qlvGetRowData(rw.stagedFiles) == []
    assert {"apple.txt", "banana.txt", "cherry.txt"} <= set(qlvGetRowData(rw.dirtyFiles))


def testShiftStageAllScopedToActiveFilter(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/apple.txt", "a")
    writeFile(f"{wd}/banana.txt", "b")
    rw = mainWindow.openRepo(wd)
    area = rw.diffArea

    rw.dirtyFiles.searchBar.popUp()
    QTest.keyClicks(rw.dirtyFiles.searchBar.lineEdit, "banana")
    assert qlvGetRowData(rw.dirtyFiles) == ["banana.txt"]

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    area.stageButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)

    assert qlvGetRowData(rw.stagedFiles) == ["banana.txt"]  # only the visible file
    QTest.keyPress(rw.dirtyFiles.searchBar.lineEdit, Qt.Key.Key_Escape)
    assert "apple.txt" in qlvGetRowData(rw.dirtyFiles)  # apple stayed unstaged


def testShiftCommitButtonRunsCommitAndPush(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    writeFile(f"{wd}/pushme.txt", "via the button")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    rw.diffArea.commitButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)

    dialog: CommitDialog = findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "pushed from the button")
    dialog.acceptButton.click()

    localTip = rw.repo.branches.local["master"].target
    assert rw.repo.branches.remote["localfs/master"].target == localTip
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_shiftbuttons.py -v`
Expected: the four new tests FAIL (`text() == "Stage"` still true under Shift; click paths stage only the selection / run plain NewCommit which never pushes). Task 4's three tests still PASS.

- [ ] **Step 3: Implement the All-variants on the file lists**

In `gitfourchette/filelists/dirtyfiles.py`, after `stage()` (line 134):

```python
    def stageAll(self):
        # Fork: Shift+Stage — stage every VISIBLE row (an active filter scopes this).
        deltas = list(self.flModel.deltas)
        if deltas:
            StageFiles.invoke(self, deltas)
```

In `gitfourchette/filelists/stagedfiles.py`, after `unstage()` (line 81):

```python
    def unstageAll(self):
        # Fork: Shift+Unstage — unstage every VISIBLE row (an active filter scopes this).
        deltas = list(self.flModel.deltas)
        if deltas:
            UnstageFiles.invoke(self, deltas)
```

- [ ] **Step 4: Implement the swap in DiffArea**

In `gitfourchette/diffarea.py`:

1. Extend the tasks import (line 26):

```python
from gitfourchette.tasks import TaskBook, AmendCommit, CommitAndPush, NewCommit, NewStash
```

2. In `__init__`, after `self.diffButtons.refreshPrefs()` (line 86):

```python
        # Fork: Shift swaps Stage/Unstage/Commit into their All/Push variants.
        self._shiftButtonsEngaged = False
        GFApplication.instance().installEventFilter(self)
```

3. In `_makeDirtyContainer`, replace `stageButton.clicked.connect(dirtyFiles.stage)` with:

```python
        stageButton.clicked.connect(self._onStageButtonClicked)
```

and replace `dirtyFiles.selectedCountChanged.connect(lambda n: stageButton.setEnabled(n > 0))` with:

```python
        dirtyFiles.selectedCountChanged.connect(lambda n: self._refreshShiftableButtons())
```

(Leave the discard connections untouched.)

4. In `_makeStageContainer`, replace `unstageButton.clicked.connect(stagedFiles.unstage)` and `stagedFiles.selectedCountChanged.connect(lambda n: unstageButton.setEnabled(n > 0))` and `commitButton.clicked.connect(lambda: NewCommit.invoke(self))` with:

```python
        unstageButton.clicked.connect(self._onUnstageButtonClicked)
        stagedFiles.selectedCountChanged.connect(lambda n: self._refreshShiftableButtons())
        commitButton.clicked.connect(self._onCommitButtonClicked)
```

5. Add the new methods to `DiffArea` (place them after `applyCustomStyling`):

```python
    # -------------------------------------------------------------------------
    # Fork: Shift-modifier button variants (Fork.dev-style)

    def eventFilter(self, watched, event):
        et = event.type()
        if et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() == Qt.Key.Key_Shift:
                self.setShiftButtonsEngaged(et == QEvent.Type.KeyPress)
        elif et == QEvent.Type.WindowDeactivate and watched is self.window():
            self.setShiftButtonsEngaged(False)  # don't stick after Alt-Tab
        return False

    def setShiftButtonsEngaged(self, engaged: bool):
        if engaged == self._shiftButtonsEngaged:
            return
        self._shiftButtonsEngaged = engaged
        self._refreshShiftableButtons()

    def _refreshShiftableButtons(self):
        if self._shiftButtonsEngaged:
            self.stageButton.setText(_("Stage All"))
            self.unstageButton.setText(_("Unstage All"))
            self.commitButton.setText(_("Commit and Push"))
            self.stageButton.setEnabled(not self.dirtyFiles.isEmpty())
            self.unstageButton.setEnabled(not self.stagedFiles.isEmpty())
        else:
            self.stageButton.setText(_("Stage"))
            self.unstageButton.setText(_("Unstage"))
            self.commitButton.setText(_p("verb", "Commit"))
            self.stageButton.setEnabled(bool(self.dirtyFiles.selectedIndexes()))
            self.unstageButton.setEnabled(bool(self.stagedFiles.selectedIndexes()))

    def _wantShiftVariant(self) -> bool:
        # Check live modifiers too so a fast Shift+click works even before
        # the label swap repaints.
        modifiers = QGuiApplication.keyboardModifiers()
        return self._shiftButtonsEngaged or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

    def _onStageButtonClicked(self):
        if self._wantShiftVariant():
            self.dirtyFiles.stageAll()
        else:
            self.dirtyFiles.stage()

    def _onUnstageButtonClicked(self):
        if self._wantShiftVariant():
            self.stagedFiles.unstageAll()
        else:
            self.stagedFiles.unstage()

    def _onCommitButtonClicked(self):
        if self._wantShiftVariant():
            CommitAndPush.invoke(self)
        else:
            NewCommit.invoke(self)
```

Note: the swapped strings are plain `_("Stage All")` etc. — new localization entries; no mnemonics (tool buttons).

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_shiftbuttons.py test/test_filelist.py test/test_tasks_commit.py -v`
Expected: all PASS. (`test_tasks_commit.py` clicks `commitButton` for plain commits — routing through `_onCommitButtonClicked` must leave it green.)

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/diffarea.py gitfourchette/filelists/dirtyfiles.py gitfourchette/filelists/stagedfiles.py test/test_shiftbuttons.py
git commit -m "feat: Shift swaps staging buttons to Stage All / Unstage All / Commit and Push"
```

---

### Task 6: Main-worktree markers (sidebar home icon + [M] tab prefix)

**Files:**
- Modify: `gitfourchette/sidebar/sidebarmodel.py:585-590` (drop "(main)" suffix), `:~1029` (icon key), `gitfourchette/repomodel.py` (new helper), `gitfourchette/repowidget.py:371-372` (`getTitle`), `gitfourchette/tasks/jumptasks.py:~790` (nameChange on worktree change)
- Test: `test/test_worktrees.py`

**Interfaces:**
- Consumes: `WorktreeInfo` (`.isMain`, `.path`), `RepoModel.worktrees`, `worktreeName(wt)` (already imported in sidebarmodel), `RepoWidget.nameChange` signal (already wired to `MainWindow.refreshAllTabTexts` via `onRepoNameChanged`), test helper `_openRepoWithLinkedWorktree(tempDir, mainWindow)` in `test/test_worktrees.py:112`.
- Produces: `RepoModel.isMainWorktreeWithLinkedWorktrees() -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_worktrees.py` (add `import os` and `from gitfourchette.sidebar.sidebarmodel import SidebarItem, SidebarModel` to its imports if not already present):

```python
def testMainWorktreeMarkers(tempDir, mainWindow):
    rw, wd = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    # Tab title gets the [M] prefix (repo has a linked worktree)
    tabText = mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex())
    assert tabText.startswith("[M] ")

    # Sidebar: main worktree row -> home icon, no "(main)" suffix
    sm = rw.sidebar.sidebarModel
    wtHeader = sm.rootNode.findChild(SidebarItem.WorktreesHeader)
    mainNode = next(n for n in wtHeader.children
                    if os.path.realpath(n.data) == os.path.realpath(rw.repo.workdir))
    linkedNode = next(n for n in wtHeader.children if n is not mainNode)

    assert "(main)" not in mainNode.displayName
    mainIndex = rw.sidebar.nodeToFilterIndex(mainNode)
    linkedIndex = rw.sidebar.nodeToFilterIndex(linkedNode)
    assert mainIndex.data(SidebarModel.Role.IconKey) == "SP_DirHomeIcon"
    assert linkedIndex.data(SidebarModel.Role.IconKey) == "SP_DirIcon"


def testNoMainMarkerWithoutLinkedWorktrees(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    mainWindow.openRepo(wd)
    tabText = mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex())
    assert not tabText.startswith("[M] ")


def testMainMarkerFollowsWorktreeAddAndRemove(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert not mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex()).startswith("[M] ")

    runShellScript("git worktree add ../MarkerWT no-parent", wd)
    rw.refreshRepo()
    assert mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex()).startswith("[M] ")

    runShellScript("git worktree remove ../MarkerWT", wd)
    rw.refreshRepo()
    assert not mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex()).startswith("[M] ")
```

(`_openRepoWithLinkedWorktree` returns whatever it returns today — check its body at `test/test_worktrees.py:112` and unpack accordingly; if it only returns `rw`, derive `wd` from `rw.repo.workdir`. Adjust the first line of the test to the actual signature, keeping the assertions identical.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: the three new tests FAIL (`tabText` has no prefix; `displayName` contains "(main)"; icon key is `SP_DirIcon`). All pre-existing worktree tests still PASS — **exception:** any test that asserts the "(main)" suffix (e.g. in `testWorktreesSidebarSection`) will now legitimately fail at Step 4; adapt those assertions to the new display (name without suffix) as part of Step 4, since dropping the suffix is precisely this task's spec.

- [ ] **Step 3: Implement**

1. `gitfourchette/sidebar/sidebarmodel.py`, worktree node construction (~line 585) — drop the suffix:

```python
        for wt in repoModel.worktrees:
            node = SidebarNode(SidebarItem.Worktree, wt.path)
            node.displayName = worktreeName(wt)
```

(Delete the `if wt.isMain: name = _("{0} (main)", name)` lines; keep the warning lines below unchanged.)

2. `gitfourchette/sidebar/sidebarmodel.py`, `data()` Worktree branch, `iconKeyRole` case (~line 1029) — the `wt` variable is already looked up at the top of the branch:

```python
            elif iconKeyRole:
                if node.warning:
                    return "achtung"
                # Fork: home icon marks the main worktree
                return "SP_DirHomeIcon" if wt is not None and wt.isMain else "SP_DirIcon"
```

3. `gitfourchette/repomodel.py` — add helper method to `RepoModel` (near `shortName`, line ~380), and `import os` at the top if absent:

```python
    def isMainWorktreeWithLinkedWorktrees(self) -> bool:
        """Fork: True when this repo is the MAIN worktree of a repo that has
        at least one linked worktree ([M] tab marker)."""
        worktrees = self.worktrees
        if len(worktrees) < 2:
            return False
        workdir = os.path.realpath(self.repo.workdir)
        return any(wt.isMain and os.path.realpath(wt.path) == workdir
                   for wt in worktrees)
```

4. `gitfourchette/repowidget.py`, `getTitle` (line 371):

```python
    def getTitle(self) -> str:
        title = self.repoModel.shortName
        if self.repoModel.isMainWorktreeWithLinkedWorktrees():
            title = _("[M] {0}", title)
        return title
```

5. `gitfourchette/tasks/jumptasks.py`, in `RefreshRepo` right after the `if anyChanges:` sidebar-refresh block (~line 792):

```python
        # Fork: [M] tab marker appears/disappears with the worktree list
        if worktreesChanged:
            rw.nameChange.emit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py test/test_sidebar.py test/test_gitfourchette.py test/test_tabbar.py -v`
Expected: all PASS. Pre-existing assertions about the "(main)" suffix (if any) get adapted here — suffix-drop is spec'd; every other adaptation is forbidden.

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/sidebar/sidebarmodel.py gitfourchette/repomodel.py gitfourchette/repowidget.py gitfourchette/tasks/jumptasks.py test/test_worktrees.py
git commit -m "feat: main-worktree markers (home icon in sidebar, [M] tab prefix)"
```

---

### Task 7: Integration pass

**Files:**
- No product code (fix-only if the suite finds interactions)

**Interfaces:**
- Consumes: everything above.
- Produces: green full suite; ledger update.

- [ ] **Step 1: Full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 0 failed (baseline was 1041 passed / 16 skipped; expect ~1055+ passed). Rerun any failure in isolation before treating it as real (PySide6/PyQt6 env footgun).

- [ ] **Step 2: Ruff on changed files**

Run: `.venv/bin/ruff check gitfourchette/sidebar/sidebardelegate.py gitfourchette/repomodel.py gitfourchette/filelists gitfourchette/tasks/commitpushtasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/tasks/jumptasks.py gitfourchette/diffarea.py gitfourchette/repowidget.py test/test_shiftbuttons.py`
Expected: no NEW findings (CI runs ruff; a red pipeline is a failed task).

- [ ] **Step 3: Sanity import + version**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -c "import gitfourchette.mainwindow; from gitfourchette.appconsts import APP_VERSION; print(APP_VERSION)"`
Expected: prints the `+fork` version, no traceback.

- [ ] **Step 4: Update ledger and commit (if anything changed)**

Append one line to `/home/admin/workspace.personal/gitfourchette/.superpowers/sdd/progress.md` summarizing: tasks complete, suite counts, deviations (if any). Commit only files changed by fixes in this task (ledger is git-ignored):

```bash
git add -u
git commit -m "test: integration pass for sidebar & staging UX batch"
```

(Skip the commit if the working tree is clean.)

Manual GUI smoke (deferred to user, note in ledger): indent look under Breeze, Shift-swap feel + no button-width jump annoyance, filter behavior with real repos, hide-pairing eye states, home icon rendering, [M] on the real gitfourchette main tab.

---

## Plan Self-Review Notes

- Spec coverage: feature 1 → Task 1; feature 2 → Tasks 4+5 (incl. dropdown-unchanged: the menu wiring is untouched); feature 3 → Task 3; feature 4 → Task 2 (incl. gone-upstream guard test); feature 5 → Task 6 (incl. nameChange refresh hook). Sequencing note from spec is obsolete: worktree-followup already merged.
- `NewCommit` rejection verified to raise `AbortTask` (`committasks.py:110`) — Task 4's cancel test relies on it.
- `SearchBar` debounce is 0ms in APP_TESTMODE, and `_termChanged` fires synchronously inside `setTerm`, so filter tests need no waits.
- Recursion guard: `setFilterTerm` no-ops on identical term, breaking the reset → `reevaluateSearchTerm` → `setTerm` cycle.
- The `escamp()` wrapper in `refreshAllTabTexts` escapes ampersands only — `[M] ` passes through verbatim.
