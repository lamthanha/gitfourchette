# Phase 3: Worktree Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sidebar "Worktrees" section (list, open-as-tab) plus `NewWorktree`, `RemoveWorktree`, `PruneWorktrees` tasks and a "Checkout in New Worktree…" branch action — the Fork.dev worktree workflow.

**Architecture:** A new fork-owned module `gitfourchette/worktrees.py` parses `git worktree list --porcelain` into `WorktreeInfo` records; `RepoModel.syncWorktrees()` caches them per refresh (same shape as `syncSubmodules`). The sidebar gains tail-appended `WorktreesHeader`/`Worktree` items rendered like the Submodules section, with open-as-tab reusing the `openRepo` signal chain. Mutations run the real git binary via `RepoTask.flowCallGit` in a new `gitfourchette/tasks/worktreetasks.py`; the NewWorktree dialog is hand-built (RebaseTodoDialog style, no .ui file).

**Tech Stack:** PyQt6, pygit2 (reads only), real git binary via GitDriver, pytest offscreen.

**Spec:** `docs/superpowers/specs/2026-07-24-gitfourchette-fork-design.md`, section "Phase 3 — Worktrees".

## Sanctioned deviations from the spec (decided at plan time — do not "fix" these back)

1. **No `OpenWorktree` task class.** Opening is a pure UI navigation (no git mutation, no flow) — it uses the Submodule pattern instead: a `Sidebar.openWorktreeRepo = Signal(str)` chained through `RepoWidget.openRepo` → `MainWindow.openRepoNextTo`. Registering a task that only emits a signal would be taskbook boilerplate. Surface in the final summary.
2. **`TaskEffects` gains no `Worktrees` flag.** Worktree tasks set `TaskEffects.Refs`, and `syncWorktrees()` is gated on `Refs | Head` — same idiom as submodules ("no TaskEffects.Submodules, so .Refs is the next best thing", submoduletasks.py:105-109).
3. **`PruneWorktrees` runs without a confirm dialog** — prune only deletes stale admin entries (never working files) and is idempotent; its header-menu entry stays always-enabled.

## Global Constraints

- Test runner prefix: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` from the worktree root. Full suite must be **0 failed** on top of baseline (1021 passed / 16 skipped at branch point `bf693995`).
- Mutations run the real git binary via `RepoTask.flowCallGit(...)` — NEVER reimplement worktree add/remove/prune in pygit2. pygit2 is for reads only. `git worktree list --porcelain` (a read) goes through `GitDriver.runSync`.
- **This phase DOES edit `tasks/__init__.py` and `taskbook.py`** (unlike the tab-colors feature): CLAUDE.md mandates registering new tasks in BOTH — `tasks/__init__.py` gets its own `from gitfourchette.tasks.worktreetasks import (...)` block (names alphabetized within the block, block placed after the rebasetasks block), `TaskBook.names` entries go at their alphabetically-correct slots. NO `TaskBook.icons` entries (fork rule — no icon assets).
- `SidebarItem` members `WorktreesHeader` and `Worktree` are appended AT THE ENUM TAIL (after `StarredHeader`) — never inserted among existing members. The delegate's canned-string check (`sidebardelegate.py` ~line 249: `node.kind <= SidebarItem.SubmodulesHeader or node.kind == SidebarItem.StarredHeader`) must be extended with `or node.kind == SidebarItem.WorktreesHeader`.
- `Branch.is_checked_out()` is worktree-wide — NEVER use it to mean "current branch". Not needed in this plan; do not introduce it.
- UI strings `_("...")`/`_p("...")` localized, typographic `…`; every new `&X` mnemonic unique within its menu. Free letters in the LocalBranch context menu include W (taken: S M o F l P U n D B C r H A).
- The Worktrees sidebar section is ALWAYS visible (like Stashes/Submodules — header with 0-N children), NOT conditionally dropped like Starred. Not in `HideableItems`/`StarrableItems`/`ForceExpand`; not added to `defaultCollapseCache` (expanded by default).
- TDD; one commit per task with trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Sidebar code is under active parallel iteration (star/eye bands, 05e595d5) — keep sidebar edits surgical and away from `SidebarClickZone`/band-painting regions of sidebardelegate.py.

## Verified codebase facts (from exploration — do not re-derive)

- `SidebarItem` enum: `gitfourchette/sidebar/sidebarmodel.py:31-50`, tail member is `StarredHeader`. `SidebarLayout` (74-131): `RootItems` (75-90, Submodules last, spacers between sections), `NonleafItems` (96-107), `UnindentItems` (109-119, leaf kinds are `-1`). `SidebarNode(kind, data)` carries `data: str`, `displayName`, `warning`; `getCollapseHash()` = `f"{kind.name}.{data}"`.
- `SidebarModel.rebuild(repoModel)` (364-541): root nodes from `SidebarLayout.RootItems`, headers resolved via `findChild`; Stashes populated at 518-526, Submodules at 528-536 (`node.warning = _("Submodule not initialized.")` pattern). `SidebarModel.data()` (650-904) dispatches per kind; generic header fallback at 882-898 auto-captions via `TrTables.enum(item)` and appends `(N)` when collapsed.
- Captions: `trtables.py` ~192-209, `SidebarItem:` dict — add `WorktreesHeader` and `Worktree` entries.
- Context menus: `Sidebar.makeNodeMenu(node)` (`sidebar.py:159-554`) `if/elif` chain; Submodule case at 524-545 is the open-as-tab analog (`self.openSubmoduleRepo.emit(data)`); SubmodulesHeader bulk-action case at 517-522. Stash case shows `TaskBook.action(self, TaskClass, accel="X", taskArgs=...)` usage.
- Double-click: `Sidebar.wantEnterNode(node)` (632-682); Submodule → `self.openSubmoduleRepo.emit(node.data)`; StashesHeader → `NewStash.invoke(self)`; default `QApplication.beep()`.
- Open-as-tab chain: `Sidebar.openSubmoduleRepo = Signal(str)` (sidebar.py:36) → connected in `RepoWidget.__init__` (repowidget.py:187) → `RepoWidget.openSubmoduleRepo(key)` (436-438) does `self.openRepo.emit(path, NavLocator())` → MainWindow (mainwindow.py:682) → `openRepoNextTo` (963-967). A `RepoTask` can emit directly: `self.rw.openRepo.emit(path, NavLocator())` (`self.rw` is the RepoWidget, repotask.py:277-283).
- Refresh: `RepoModel.syncSubmodules()` (repomodel.py:330-340) is the sync template (compute, compare, assign, return changed-bool); primed in `RepoModel.__init__` (~225-226). `RefreshRepo.flow` (jumptasks.py:683-799) calls syncs at 742-759 under effect-flag gates and folds change-bools into `anyChanges` at 778-783 → `rw.sidebar.refresh(repoModel)`. The sync block runs off the UI thread — synchronous subprocess calls are acceptable there.
- `GitDriver.runSync(*args, directory="", strict=False)` (gitdriver/gitdriver.py:61-68) prepends the git binary; returns stdout str, `""` on failure (non-strict). Read-usage template: `GitDriver.runSync(*tokens, directory=self.repo.workdir, strict=True)` (filelists/filelist.py:608-609 — copy that file's import).
- `flowCallGit(self, *args, customKey="", workdir="", env=None, autoFail=False) -> Generator[..., GitDriver]` (repotask.py:514-524); on failure `raise AbortTask(driver.htmlErrorText())` (rebasetasks.py:411). Effects via `self.epilog.effects |= TaskEffects.Refs | ...` (rebasetasks.py `_flowRebaseGit`). `flowConfirm(text=..., verb=..., ...)` raises `AbortTask("")` when rejected; `flowDialog(dlg)` likewise on rejection.
- Task registration precedent: rebasetasks import block in `tasks/__init__.py:28-36`; `TaskBook.names` (taskbook.py:31-112) alphabetical by class name; `TaskBook.action(invoker, taskClass, name="", accel="", taskArgs=None, **kwargs)` (taskbook.py:251-287) — `accel="X"` auto-inserts `&` in the auto-generated name.
- Hand-built dialog precedent: `forms/rebasetododialog.py` (plain QDialog, manual `_revalidate()` + `okButton.setEnabled`); path-validation precedent: `clonedialog.py:108-119` (`validatePath`), browse via `PersistentFileDialog.saveFile(self, "Key", caption, initialName)` (clonedialog.py:245). Branch-name validation helper: `nameValidationMessage` (see forms/newbranchdialog.py imports).
- Tests: `runShellScript("git worktree add ../linked-wt master", wd)` precedent (test_tasks_rebase.py:231-241); sidebar helpers `sb.findNodeByKind/findNodesByKind/findNode` (sidebar.py:903-927); `triggerMenuAction(sb.makeNodeMenu(node), pattern)`; `findQDialog(rw, titlePattern)`; `acceptQMessageBox(rw, textPattern)` / `rejectQMessageBox`; canned repo `unpackRepo(tempDir)` (trailing slash). Tests needing `runShellScript` must take the `mainWindow` fixture.
- Main-root derivation precedent (no pygit2): `tabcolors._commonGitDir/repoBindingKey`. In tasks, prefer `repoModel.worktrees` (the cached list) — its first record `isMain=True` carries the main worktree path.
- `MainWindow.tabWidgetForWorkdirPath(workdir)` (mainwindow.py:464) returns the open tab widget or None; reach MainWindow from a task via `GFApplication.instance().mainWindow`.
- Baseline: 1021 passed / 16 skipped at `bf693995`. Ruff: repo is fully green under the (now frozen+pinned) configured rules — new files must stay clean (`.venv/bin/python -m ruff check` at repo root).

---

### Task 1: Worktree listing — parser, model field, refresh wiring

**Files:**
- Create: `gitfourchette/worktrees.py`
- Create: `test/test_worktrees.py`
- Modify: `gitfourchette/repomodel.py` (field + `syncWorktrees` + prime call, next to submodules)
- Modify: `gitfourchette/tasks/jumptasks.py` (sync call + `anyChanges` fold, ~lines 742-783)

**Interfaces produced (Tasks 2-4 rely on):**
- `worktrees.WorktreeInfo` frozen dataclass: `path: str`, `head: str`, `branch: str` (full refname, `""` when detached/bare), `isMain: bool`, `isBare: bool`, `isDetached: bool`, `locked: bool`, `lockedReason: str`, `prunable: bool`, `prunableReason: str`
- `worktrees.parseWorktreeListPorcelain(text: str) -> list[WorktreeInfo]`
- `worktrees.listWorktrees(workdir: str) -> list[WorktreeInfo]`
- `RepoModel.worktrees: list[WorktreeInfo]`; `RepoModel.syncWorktrees() -> bool`

- [ ] **Step 1: Write the failing tests** — create `test/test_worktrees.py`:

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension tests — Phase 3 worktree management.
# -----------------------------------------------------------------------------

import os

from gitfourchette import worktrees
from .util import *

SAMPLE_PORCELAIN = """\
worktree /home/u/repo
HEAD 1111111111111111111111111111111111111111
branch refs/heads/master

worktree /home/u/repo-feature
HEAD 2222222222222222222222222222222222222222
branch refs/heads/feature

worktree /home/u/repo-detached
HEAD 3333333333333333333333333333333333333333
detached

worktree /home/u/repo-locked
HEAD 4444444444444444444444444444444444444444
branch refs/heads/locky
locked demo of a lock reason

worktree /home/u/repo-gone
HEAD 5555555555555555555555555555555555555555
branch refs/heads/gone
prunable gitdir file points to non-existent location
"""

BARE_PORCELAIN = """\
worktree /home/u/bare.git
bare

worktree /home/u/wt
HEAD 6666666666666666666666666666666666666666
branch refs/heads/main
"""


def testParseWorktreeListPorcelain():
    infos = worktrees.parseWorktreeListPorcelain(SAMPLE_PORCELAIN)
    assert [wt.path for wt in infos] == [
        "/home/u/repo", "/home/u/repo-feature", "/home/u/repo-detached",
        "/home/u/repo-locked", "/home/u/repo-gone"]
    assert [wt.isMain for wt in infos] == [True, False, False, False, False]
    main = infos[0]
    assert main.branch == "refs/heads/master"
    assert main.head.startswith("1111")
    assert not (main.isBare or main.isDetached or main.locked or main.prunable)
    detached = infos[2]
    assert detached.isDetached and detached.branch == ""
    locked = infos[3]
    assert locked.locked and locked.lockedReason == "demo of a lock reason"
    gone = infos[4]
    assert gone.prunable and "non-existent" in gone.prunableReason


def testParseWorktreeListPorcelainBareAndEmpty():
    infos = worktrees.parseWorktreeListPorcelain(BARE_PORCELAIN)
    assert infos[0].isBare and infos[0].isMain and infos[0].branch == ""
    assert not infos[1].isBare and infos[1].branch == "refs/heads/main"
    assert worktrees.parseWorktreeListPorcelain("") == []
    assert worktrees.parseWorktreeListPorcelain("\n\n") == []


def testListWorktreesRealRepo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    infos = worktrees.listWorktrees(wd)
    assert len(infos) == 1
    assert infos[0].isMain
    assert os.path.realpath(infos[0].path) == os.path.realpath(wd)

    runShellScript("git worktree add ../LinkedWT master", wd)
    infos = worktrees.listWorktrees(wd)
    assert len(infos) == 2
    assert infos[1].branch == "refs/heads/master"
    assert not infos[1].isMain

    # Listing works from the linked worktree too, and not-a-repo yields []
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    assert [wt.path for wt in worktrees.listWorktrees(linked)] == [wt.path for wt in infos]
    assert worktrees.listWorktrees(tempDir.name) == []


def testSyncWorktreesDetectsChanges(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    model = rw.repoModel
    assert len(model.worktrees) == 1  # primed at load
    assert not model.syncWorktrees()  # no change

    runShellScript("git worktree add ../LinkedWT master", wd)
    assert model.syncWorktrees()      # change detected
    assert len(model.worktrees) == 2
    assert not model.syncWorktrees()  # stable again
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'gitfourchette.worktrees'`.

- [ ] **Step 3: Create `gitfourchette/worktrees.py`:**

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — not part of upstream GitFourchette.
# Worktree enumeration via `git worktree list --porcelain` (reads only;
# worktree mutations live in gitfourchette/tasks/worktreetasks.py).
# -----------------------------------------------------------------------------

import dataclasses

from gitfourchette.gitdriver import GitDriver


@dataclasses.dataclass(frozen=True)
class WorktreeInfo:
    path: str
    head: str = ""
    branch: str = ""
    "Full refname of the checked-out branch; empty when detached or bare."
    isMain: bool = False
    isBare: bool = False
    isDetached: bool = False
    locked: bool = False
    lockedReason: str = ""
    prunable: bool = False
    prunableReason: str = ""


def parseWorktreeListPorcelain(text: str) -> list[WorktreeInfo]:
    """Parse `git worktree list --porcelain` output (blank-line-separated records).
    The first record is always the main worktree (or the bare repo itself)."""
    infos = []
    records = [r for r in text.strip().split("\n\n") if r.strip()]
    for i, record in enumerate(records):
        fields: dict = {"isMain": i == 0}
        for line in record.splitlines():
            key, _sep, value = line.partition(" ")
            if key == "worktree":
                fields["path"] = value
            elif key == "HEAD":
                fields["head"] = value
            elif key == "branch":
                fields["branch"] = value
            elif key == "bare":
                fields["isBare"] = True
            elif key == "detached":
                fields["isDetached"] = True
            elif key == "locked":
                fields["locked"] = True
                fields["lockedReason"] = value
            elif key == "prunable":
                fields["prunable"] = True
                fields["prunableReason"] = value
            # Unknown keys from future git versions are ignored.
        if fields.get("path"):
            infos.append(WorktreeInfo(**fields))
    return infos


def listWorktrees(workdir: str) -> list[WorktreeInfo]:
    """List all worktrees of the repo containing workdir ([] on any git failure)."""
    stdout = GitDriver.runSync("worktree", "list", "--porcelain", directory=workdir)
    if not stdout:
        return []
    return parseWorktreeListPorcelain(stdout)
```

(Verify the `GitDriver` import path against `gitfourchette/filelists/filelist.py`'s import and match it exactly.)

- [ ] **Step 4: RepoModel field + sync.** In `gitfourchette/repomodel.py`, next to the `submodules` field declarations (~126-134) add the field, and next to `syncSubmodules` (~330-340) add:

```python
    def syncWorktrees(self) -> bool:
        from gitfourchette.worktrees import listWorktrees
        fresh = listWorktrees(self.repo.workdir)
        if fresh == self.worktrees:
            return False
        self.worktrees = fresh
        return True
```

Prime it in `__init__` right where `syncSubmodules()` is primed (~225-226): initialize `self.worktrees = []` with the other field inits, then call `self.syncWorktrees()` beside `self.syncSubmodules()`. Follow the file's existing style for field declaration vs `__init__` assignment (mirror exactly what `submodules` does).

- [ ] **Step 5: Refresh wiring.** In `gitfourchette/tasks/jumptasks.py`, in `RefreshRepo.flow`'s sync block (~742-759) add alongside the existing syncs:

```python
        worktreesChanged = False
        if effectFlags & (TaskEffects.Refs | TaskEffects.Head):
            worktreesChanged = repoModel.syncWorktrees()
```

and fold `| worktreesChanged` into the `anyChanges = ...` expression (~780).

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: 4 passed.

- [ ] **Step 7: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1025 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/worktrees.py gitfourchette/repomodel.py gitfourchette/tasks/jumptasks.py test/test_worktrees.py
git commit -m "feat: worktree listing model (porcelain parser + per-refresh sync)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Sidebar "Worktrees" section + open-as-tab

**Files:**
- Modify: `gitfourchette/sidebar/sidebarmodel.py` (enum tail, layout lists, rebuild population, `data()` case)
- Modify: `gitfourchette/sidebar/sidebardelegate.py` (extend `isCannedString` — ONE line)
- Modify: `gitfourchette/sidebar/sidebar.py` (signal, leaf/header menu cases, `wantEnterNode` cases)
- Modify: `gitfourchette/repowidget.py` (connect signal + tiny slot)
- Modify: `gitfourchette/trtables.py` (two `SidebarItem` caption entries)
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: `RepoModel.worktrees` (Task 1).
- Produces: `SidebarItem.WorktreesHeader`, `SidebarItem.Worktree` (node `data` = worktree absolute path as reported by git); `Sidebar.openWorktreeRepo = Signal(str)`. Task 3/4 append `TaskBook.action` entries to the two menu cases created here.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def _openRepoWithLinkedWorktree(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT master", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    rw = mainWindow.openRepo(wd)
    return wd, linked, rw


def testWorktreesSidebarSection(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    nodes = rw.sidebar.findNodesByKind(SidebarItem.Worktree)
    assert len(nodes) == 2
    assert nodes[0].parent is header

    mainNode, linkedNode = nodes
    assert os.path.realpath(mainNode.data) == os.path.realpath(wd)
    assert "(main)" in mainNode.displayName
    assert os.path.realpath(linkedNode.data) == os.path.realpath(linked)
    assert "(main)" not in linkedNode.displayName
    assert linkedNode.displayName.startswith("LinkedWT")


def testWorktreesSectionAlwaysVisibleEvenWithoutLinked(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    assert len(header.children) == 1  # just the main worktree row


def testWorktreesListedFromLinkedWorktreeTab(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT master", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    rw = mainWindow.openRepo(linked)
    nodes = rw.sidebar.findNodesByKind(SidebarItem.Worktree)
    assert len(nodes) == 2
    assert "(main)" in nodes[0].displayName


def testOpenWorktreeInNewTab(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    assert mainWindow.tabs.count() == 1

    linkedNode = rw.sidebar.findNode(
        lambda n: n.kind == SidebarItem.Worktree and os.path.realpath(n.data) == os.path.realpath(linked))
    triggerMenuAction(rw.sidebar.makeNodeMenu(linkedNode), r"open worktree in new tab")
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(linked)

    # Double-click (wantEnterNode) opens/focuses too — no duplicate tab
    mainWindow.tabs.setCurrentIndex(0)
    rw.sidebar.wantEnterNode(linkedNode)
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(linked)


def testWorktreeSidebarRefreshAfterExternalChange(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1

    runShellScript("git worktree add ../LinkedWT master", wd)
    rw.refreshRepo()  # autoRefresh path picks up external changes
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2
```

(If `rw.refreshRepo()` alone doesn't route through the `Refs|Head` gate, use the same refresh-forcing idiom neighboring tests use — check how test_sidebar.py forces a full refresh — but do NOT weaken the assertion.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: Task 1's 4 pass; the 5 new tests FAIL (`AttributeError: WorktreesHeader`).

- [ ] **Step 3: Sidebar model edits** in `gitfourchette/sidebar/sidebarmodel.py`:

(a) Enum tail (after `StarredHeader`):

```python
    WorktreesHeader = enum.auto()
    Worktree = enum.auto()
```

(b) `SidebarLayout.RootItems`: append a `SidebarItem.Spacer` + `SidebarItem.WorktreesHeader` after the Submodules entry (end of list). `NonleafItems`: add `SidebarItem.WorktreesHeader`. `UnindentItems`: add `SidebarItem.Worktree: -1`. Do NOT touch `ForceExpand`/`HideableItems`/`StarrableItems`.

(c) In `rebuild()`, resolve the header beside the other `findChild` calls (~406-407):

```python
        worktreeRoot = rootNode.findChild(SidebarItem.WorktreesHeader)
```

and populate right after the Submodules loop (~536):

```python
        # Worktrees
        for wt in repoModel.worktrees:
            node = SidebarNode(SidebarItem.Worktree, wt.path)
            name = os.path.basename(os.path.normpath(wt.path))
            if wt.isMain:
                name = _("{0} (main)", name)
            node.displayName = name
            if wt.prunable:
                node.warning = _("This worktree can be pruned.")
            elif wt.locked:
                node.warning = _("Worktree is locked.") if not wt.lockedReason else _("Worktree is locked: {0}", wt.lockedReason)
            worktreeRoot.appendChild(node)
```

(Match the file's localization call style — if `_("{0} (main)", name)` positional-args form isn't used elsewhere in this file, use the file's `.format`-style equivalent. Check `os` is already imported.)

(d) In `data()`, add a `Worktree` case before the generic `else` fallback, mirroring the Submodule case (~844-858):

```python
        elif item == SidebarItem.Worktree:
            wt = next((w for w in self.repoModel.worktrees if w.path == node.data), None)
            if role == Qt.ItemDataRole.DisplayRole:
                return node.displayName
            elif role == Qt.ItemDataRole.ToolTipRole:
                lines = [escape(node.data)]
                if wt is not None and wt.branch:
                    lines.append(escape(RefPrefix.split(wt.branch)[1]))
                elif wt is not None and wt.isDetached:
                    lines.append(escape(_("Detached HEAD @ {0}", wt.head[:12])))
                if node.warning:
                    lines.append(node.warning)
                return "<p>" + "<br>".join(lines) + "</p>"
            elif role == SidebarModel.Role.IconKey:
                return "achtung" if node.warning else "SP_DirIcon"
            elif role == Qt.ItemDataRole.FontRole:
                if os.path.realpath(node.data) == os.path.realpath(self.repoModel.repo.workdir):
                    return self.boldFont()  # highlight the currently open worktree
```

(Adapt names to the actual patterns in `data()`: how the Submodule case accesses `repoModel`, builds tooltips (`escape`, paragraph joins), and how the current/home-branch case obtains its bold font — copy those idioms exactly rather than inventing new ones. The behavioral contract is: display = `displayName`; tooltip contains path + branch-or-detached + warning; icon `achtung` when warning else `SP_DirIcon`; bold for the currently open worktree.)

- [ ] **Step 4: Delegate + captions.**

`gitfourchette/sidebar/sidebardelegate.py` (~249): extend the canned-string check with `or node.kind == SidebarItem.WorktreesHeader`.

`gitfourchette/trtables.py` `SidebarItem:` dict: add

```python
            SidebarItem.WorktreesHeader : _p("SidebarModel", "Worktrees"),
            SidebarItem.Worktree        : _p("SidebarModel", "Worktrees"),
```

- [ ] **Step 5: Open-as-tab chain + menus.**

`gitfourchette/sidebar/sidebar.py`:
(a) Beside `openSubmoduleRepo` (~36): `openWorktreeRepo = Signal(str)`.
(b) In `makeNodeMenu`, add cases (mirror the Submodule/SubmodulesHeader cases; Tasks 3-4 will extend them):

```python
        elif item == SidebarItem.WorktreesHeader:
            actions += []  # populated by NewWorktree/PruneWorktrees in Tasks 3-4

        elif item == SidebarItem.Worktree:
            actions += [
                ActionDef(_("&Open Worktree in New Tab"), lambda: self.openWorktreeRepo.emit(data)),
                ActionDef(_("Open Worktree &Folder"), lambda: openFolder(data)),
                ActionDef(_("Copy &Path"), lambda: self.copyToClipboard(data)),
            ]
```

(`openFolder` — check it's importable in sidebar.py the same way mainwindow uses it (toolbox); if the Submodule case routes folder-opening through a signal instead, mirror the Submodule pattern for consistency. An empty header case is acceptable this task ONLY if `makeNodeMenu` tolerates an empty actions list — if it doesn't, put the header case in Task 3 instead and note it.)
(c) In `wantEnterNode`, add beside the Submodule case:

```python
        elif item == SidebarItem.Worktree:
            self.openWorktreeRepo.emit(node.data)
```

`gitfourchette/repowidget.py`: beside the `openSubmoduleRepo` connect (~187) add `self.sidebar.openWorktreeRepo.connect(self.openWorktreeRepo)`, and beside `openSubmoduleRepo` (~436-438):

```python
    def openWorktreeRepo(self, path: str):
        self.openRepo.emit(path, NavLocator())
```

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py test/test_sidebar.py -v`
Expected: test_worktrees 9 passed; test_sidebar fully green (no regressions from the enum/layout changes).

- [ ] **Step 7: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1030 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/sidebar/ gitfourchette/repowidget.py gitfourchette/trtables.py test/test_worktrees.py
git commit -m "feat: Worktrees sidebar section with open-as-tab

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: NewWorktree task + dialog + menu entries

**Files:**
- Create: `gitfourchette/forms/newworktreedialog.py`
- Create: `gitfourchette/tasks/worktreetasks.py`
- Modify: `gitfourchette/tasks/__init__.py` (new import block)
- Modify: `gitfourchette/tasks/taskbook.py` (`TaskBook.names` — ONLY the `NewWorktree` entry in this task; Task 4 adds its own two)
- Modify: `gitfourchette/sidebar/sidebar.py` (WorktreesHeader menu + LocalBranch menu entry)
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: `NewWorktree(RepoTask)` with `flow(self, branchName: str = "")`; `NewWorktreeDialog` with test API `setPath(str)`, `setExistingBranch(shorthand)`, `setNewBranch(name, baseRef)`, and getters `path()`, `wantNewBranch()`, `existingBranch()`, `newBranchName()`, `baseRef()`. TaskBook name: `tasks.NewWorktree: _("New worktree"),`.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def testNewWorktreeExistingBranch(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "NewWT")

    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    triggerMenuAction(rw.sidebar.makeNodeMenu(header), r"new worktree")
    dlg = findQDialog(rw, r"new worktree")
    dlg.setPath(target)
    dlg.setExistingBranch("no-parent")
    dlg.accept()

    # Offer to open the new worktree: decline first
    rejectQMessageBox(rw, r"open.+new tab")
    assert os.path.isdir(target)
    assert mainWindow.tabs.count() == 1
    # Sidebar refreshed with the new row
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2
    # The branch is checked out there
    from gitfourchette import worktrees
    infos = worktrees.listWorktrees(wd)
    assert infos[1].branch == "refs/heads/no-parent"


def testNewWorktreeNewBranchAndOpenTab(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "FreshWT")

    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    triggerMenuAction(rw.sidebar.makeNodeMenu(header), r"new worktree")
    dlg = findQDialog(rw, r"new worktree")
    dlg.setPath(target)
    dlg.setNewBranch("wtbranch", "master")
    dlg.accept()

    acceptQMessageBox(rw, r"open.+new tab")
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(target)
    assert "wtbranch" in rw.repo.branches.local


def testCheckoutBranchInNewWorktreeFromBranchMenu(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "BranchWT")

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"checkout in new worktree")
    dlg = findQDialog(rw, r"new worktree")
    assert not dlg.wantNewBranch()
    assert dlg.existingBranch() == "no-parent"  # pre-filled from the menu
    dlg.setPath(target)
    dlg.accept()
    rejectQMessageBox(rw, r"open.+new tab")

    from gitfourchette import worktrees
    assert any(wt.branch == "refs/heads/no-parent" for wt in worktrees.listWorktrees(wd))


def testNewWorktreeGitFailureSurfaced(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "FailWT")

    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    dlg.setPath(target)
    dlg.setExistingBranch("master")  # master is checked out here -> git refuses
    dlg.accept()
    acceptQMessageBox(rw, r"already used by worktree|already checked out")
    assert not os.path.isdir(target)
```

(The canned TestGitRepository has local branches `master` and `no-parent` — verify with `git branch` in the unpacked repo before finalizing test refs, and adjust the branch names in these tests to real ones if they differ; do not weaken assertions.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: 9 pass; 4 new FAIL (no "new worktree" menu entry / ImportError for NewWorktree).

- [ ] **Step 3: Create `gitfourchette/forms/newworktreedialog.py`** (hand-built, RebaseTodoDialog style):

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — dialog for the NewWorktree task (Phase 3).
# -----------------------------------------------------------------------------

import os
from pathlib import Path

from gitfourchette.localization import *
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class NewWorktreeDialog(QDialog):
    def __init__(self, repo: Repo, prefillBranch: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("NewWorktreeDialog")
        self.setWindowTitle(_("New Worktree"))

        localBranches = sorted(repo.branches.local)

        self.pathEdit = QLineEdit(self)
        browseButton = QPushButton(_("&Browse…"), self)
        browseButton.clicked.connect(self.browse)

        self.existingRadio = QRadioButton(_("Check out an &existing branch:"), self)
        self.existingCombo = QComboBox(self)
        self.existingCombo.addItems(localBranches)

        self.newRadio = QRadioButton(_("Create a &new branch:"), self)
        self.newNameEdit = QLineEdit(self)
        self.baseRefCombo = QComboBox(self)
        self.baseRefCombo.addItems(localBranches)

        if prefillBranch and prefillBranch in localBranches:
            self.existingCombo.setCurrentText(prefillBranch)
        self.existingRadio.setChecked(True)

        # Default path: sibling of the main worktree root, named <repo>-<branch>
        mainRoot = os.path.dirname(os.path.normpath(repo.commondir)) \
            if os.path.basename(os.path.normpath(repo.commondir)) == ".git" \
            else os.path.normpath(repo.commondir)
        self._mainRoot = mainRoot
        self.pathEdit.setText(self.defaultPathForBranch(self.existingCombo.currentText()))

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.okButton = buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        self.errorLabel = QLabel(self)
        self.errorLabel.setWordWrap(True)

        pathRow = QHBoxLayout()
        pathRow.addWidget(self.pathEdit)
        pathRow.addWidget(browseButton)

        newRow = QHBoxLayout()
        newRow.addWidget(self.newNameEdit)
        newRow.addWidget(QLabel(_("from:"), self))
        newRow.addWidget(self.baseRefCombo)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("&Path:"), self))
        layout.addLayout(pathRow)
        layout.addSpacing(8)
        layout.addWidget(self.existingRadio)
        layout.addWidget(self.existingCombo)
        layout.addWidget(self.newRadio)
        layout.addLayout(newRow)
        layout.addWidget(self.errorLabel)
        layout.addWidget(buttonBox)

        for signalSource in (self.pathEdit.textChanged, self.newNameEdit.textChanged,
                             self.existingRadio.toggled, self.newRadio.toggled,
                             self.existingCombo.currentTextChanged):
            signalSource.connect(self._revalidate)
        self.existingCombo.currentTextChanged.connect(self._trackDefaultPath)
        self.newNameEdit.textChanged.connect(self._trackDefaultPath)
        self._userEditedPath = False
        self.pathEdit.textEdited.connect(lambda: setattr(self, "_userEditedPath", True))
        self._revalidate()
        self.setModal(True)

    def defaultPathForBranch(self, branch: str) -> str:
        repoName = os.path.basename(self._mainRoot)
        leaf = branch.replace("/", "-") if branch else "worktree"
        return os.path.join(os.path.dirname(self._mainRoot), f"{repoName}-{leaf}")

    def _trackDefaultPath(self):
        if not self._userEditedPath:
            branch = self.newNameEdit.text() if self.wantNewBranch() else self.existingCombo.currentText()
            self.pathEdit.setText(self.defaultPathForBranch(branch))

    def _revalidate(self):
        error = ""
        p = self.pathEdit.text().strip()
        if not p:
            error = _("Enter a path for the new worktree.")
        elif Path(p).is_file():
            error = _("There’s already a file at this path.")
        elif Path(p).is_dir() and any(Path(p).iterdir()):
            error = _("This directory exists and is not empty.")
        elif self.wantNewBranch() and not self.newNameEdit.text().strip():
            error = _("Enter a name for the new branch.")
        self.errorLabel.setText(error)
        self.okButton.setEnabled(not error)

    def browse(self):
        qfd = PersistentFileDialog.saveFile(
            self, "NewWorktree", _("New worktree location"), os.path.basename(self.pathEdit.text()))
        qfd.fileSelected.connect(self.pathEdit.setText)
        qfd.fileSelected.connect(lambda: setattr(self, "_userEditedPath", True))
        qfd.show()

    # --- Test/consumer API -------------------------------------------------

    def path(self) -> str:
        return self.pathEdit.text().strip()

    def wantNewBranch(self) -> bool:
        return self.newRadio.isChecked()

    def existingBranch(self) -> str:
        return self.existingCombo.currentText()

    def newBranchName(self) -> str:
        return self.newNameEdit.text().strip()

    def baseRef(self) -> str:
        return self.baseRefCombo.currentText()

    def setPath(self, p: str):
        self._userEditedPath = True
        self.pathEdit.setText(p)

    def setExistingBranch(self, shorthand: str):
        self.existingRadio.setChecked(True)
        self.existingCombo.setCurrentText(shorthand)

    def setNewBranch(self, name: str, baseRef: str):
        self.newRadio.setChecked(True)
        self.newNameEdit.setText(name)
        self.baseRefCombo.setCurrentText(baseRef)
```

(Verify `PersistentFileDialog.saveFile`'s exact signature/signal against clonedialog.py:245 and adapt the `browse` wiring accordingly. If the codebase's dialogs prefer `QFileDialog.getExistingDirectory`-style helpers for directories, use the closest existing idiom — the behavioral contract is: browse fills pathEdit and stops auto-tracking.)

- [ ] **Step 4: Create `gitfourchette/tasks/worktreetasks.py`:**

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — Phase 3: worktree management tasks.
# Mutations run the real git binary (flowCallGit); pygit2 stays read-only.
# -----------------------------------------------------------------------------

from gitfourchette.forms.newworktreedialog import NewWorktreeDialog
from gitfourchette.localization import *
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects
from gitfourchette.toolbox import *


class NewWorktree(RepoTask):
    def flow(self, branchName: str = ""):
        dlg = NewWorktreeDialog(self.repo, branchName, self.parentWidget())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()

        path = dlg.path()
        if dlg.wantNewBranch():
            args = ["worktree", "add", "-b", dlg.newBranchName(), path, dlg.baseRef()]
        else:
            args = ["worktree", "add", path, dlg.existingBranch()]

        driver = yield from self.flowCallGit(*args, autoFail=False)
        if driver.exitCode() != 0:
            raise AbortTask(driver.htmlErrorText())

        self.epilog.effects |= TaskEffects.Refs

        openOffer = yield from self.flowConfirmOpenNewWorktree(path)
        if openOffer:
            self.rw.openRepo.emit(path, NavLocator())

    def flowConfirmOpenNewWorktree(self, path: str):
        try:
            yield from self.flowConfirm(
                title=_("Worktree created"),
                text=_("Worktree created at {0}.", bquo(compactPath(path)))
                     + "<br>" + _("Open it in a new tab?"),
                verb=_("Open"),
                cancelText=_("Not Now"))
            return True
        except AbortTask:
            return False
```

(Two things the implementer must verify empirically, adjusting mechanics but not behavior: (1) `flowConfirm`'s exact kwargs — copy a real call from rebasetasks/branchtasks; (2) whether catching `AbortTask` around `flowConfirm` cleanly continues the flow with the epilog effects intact — the decline-path test (`rejectQMessageBox` then sidebar-row assertion) is the proof. If catching is unreliable, the fallback is: complete the flow after `epilog.effects`, and show the offer via the `flowConfirm(..., actionButton=...)` result-comparison pattern from branchtasks.py:628-648. Behavior contract: accept → new tab; decline → NO abort side effects, refresh still happens.)

- [ ] **Step 5: Register the task.**

`gitfourchette/tasks/__init__.py` — after the rebasetasks block:

```python
from gitfourchette.tasks.worktreetasks import (
    NewWorktree,
)
```

`gitfourchette/tasks/taskbook.py` `TaskBook.names` — at the alphabetical slot among the `New*` entries:

```python
            tasks.NewWorktree: _("New worktree"),
```

- [ ] **Step 6: Menu entries** in `gitfourchette/sidebar/sidebar.py`:

WorktreesHeader case (from Task 2):

```python
        elif item == SidebarItem.WorktreesHeader:
            actions += [
                TaskBook.action(self, NewWorktree, accel="N"),
            ]
```

LocalBranch case — after the `New &Branch Here…` entry (~sidebar.py:298), add:

```python
        TaskBook.action(self, NewWorktree, _("Checkout in New &Worktree…"), taskArgs=branchShorthand),
```

(Use the same variable the surrounding entries use for the branch's shorthand name — inspect the neighboring `TaskBook.action` calls and match; `NewWorktree.flow`'s `branchName` expects the local-branch SHORTHAND. Also import `NewWorktree` wherever sidebar.py imports the other tasks. Add a `WorktreesHeader` double-click in `wantEnterNode`: `NewWorktree.invoke(self)`, mirroring `StashesHeader → NewStash`.)

- [ ] **Step 7: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: 13 passed.

- [ ] **Step 8: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1034 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 9: Commit**

```bash
git add gitfourchette/forms/newworktreedialog.py gitfourchette/tasks/worktreetasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/sidebar/sidebar.py test/test_worktrees.py
git commit -m "feat: NewWorktree task + dialog; checkout-in-new-worktree branch action

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: RemoveWorktree + PruneWorktrees

**Files:**
- Modify: `gitfourchette/tasks/worktreetasks.py` (two new tasks)
- Modify: `gitfourchette/tasks/__init__.py` (extend the worktreetasks block, alphabetized)
- Modify: `gitfourchette/tasks/taskbook.py` (two `TaskBook.names` entries at alphabetical slots)
- Modify: `gitfourchette/sidebar/sidebar.py` (Worktree leaf menu + WorktreesHeader menu additions)
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: `RemoveWorktree(RepoTask)` `flow(self, path: str)`; `PruneWorktrees(RepoTask)` `flow(self)`. TaskBook names: `tasks.PruneWorktrees: _("Prune worktrees"),` / `tasks.RemoveWorktree: _("Remove worktree"),`.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def _worktreeNodeByPath(rw, path):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    return rw.sidebar.findNode(
        lambda n: n.kind == SidebarItem.Worktree and os.path.realpath(n.data) == os.path.realpath(path))


def testRemoveWorktreeClean(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"remove.+worktree")

    assert not os.path.exists(linked)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1


def testRemoveWorktreeDirtyOffersForce(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    writeFile(os.path.join(linked, "dirty.txt"), "uncommitted\n")

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"remove.+worktree")
    # git refuses (dirty) -> force prompt
    acceptQMessageBox(rw, r"force")

    assert not os.path.exists(linked)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1


def testRemoveWorktreeDirtyForceDeclined(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    writeFile(os.path.join(linked, "dirty.txt"), "uncommitted\n")

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"remove.+worktree")
    rejectQMessageBox(rw, r"force")

    assert os.path.exists(linked)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2


def testRemoveMainWorktreeBlocked(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    node = _worktreeNodeByPath(rw, wd)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"main worktree")
    assert os.path.exists(os.path.normpath(wd))


def testRemoveWorktreeOpenInTabBlocked(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    mainWindow.openRepo(linked)  # open the linked worktree's tab
    mainWindow.tabs.setCurrentIndex(0)

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"remove worktree")
    acceptQMessageBox(rw, r"close.+tab")
    assert os.path.exists(linked)


def testPruneWorktrees(tempDir, mainWindow):
    import shutil
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    shutil.rmtree(linked)  # stale admin entry remains
    rw.refreshRepo()
    header = rw.sidebar.findNodeByKind(SidebarItem.WorktreesHeader)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2  # stale row still listed

    triggerMenuAction(rw.sidebar.makeNodeMenu(header), r"prune worktrees")
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 1
```

(`writeFile` is the util helper the suite uses for creating files — verify its exact name/signature in test/util.py and adjust. If the stale-row-still-listed intermediate assertion proves refresh-order dependent, drop THAT line only, keeping the post-prune assertion.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: 13 pass; 6 new FAIL (no "remove worktree"/"prune worktrees" menu entries).

- [ ] **Step 3: Implement the tasks** — append to `gitfourchette/tasks/worktreetasks.py`:

```python
class RemoveWorktree(RepoTask):
    def flow(self, path: str):
        from gitfourchette.application import GFApplication
        import os

        mainInfo = next((wt for wt in self.repoModel.worktrees if wt.isMain), None)
        if mainInfo is not None and os.path.realpath(path) == os.path.realpath(mainInfo.path):
            raise AbortTask(_("You can’t remove the main worktree."), icon="information")

        mainWindow = GFApplication.instance().mainWindow
        if mainWindow is not None and mainWindow.tabWidgetForWorkdirPath(path) is not None:
            raise AbortTask(
                _("This worktree is open in a tab. Close its tab before removing it."),
                icon="information")

        yield from self.flowConfirm(
            text=_("Really remove worktree {0}?", bquo(compactPath(path)))
                 + "<br>" + _("Its files will be deleted from disk."),
            verb=_("Remove Worktree"))

        driver = yield from self.flowCallGit("worktree", "remove", path, autoFail=False)
        if driver.exitCode() != 0:
            yield from self.flowConfirm(
                text=_("Git refused to remove this worktree "
                       "(it may contain uncommitted changes).")
                     + driver.htmlErrorText()
                     + _("Force-remove it?"),
                verb=_("Force Remove"))
            driver = yield from self.flowCallGit("worktree", "remove", "--force", path, autoFail=False)
            if driver.exitCode() != 0:
                raise AbortTask(driver.htmlErrorText())

        self.epilog.effects |= TaskEffects.Refs


class PruneWorktrees(RepoTask):
    def flow(self):
        driver = yield from self.flowCallGit("worktree", "prune", autoFail=False)
        if driver.exitCode() != 0:
            raise AbortTask(driver.htmlErrorText())
        self.epilog.effects |= TaskEffects.Refs
```

(Verify: `self.repoModel` accessor name on RepoTask — rebasetasks shows the real one; `flowConfirm` kwargs; whether `tabWidgetForWorkdirPath` needs the trailing-slash/realpath normalization — prove it with `testRemoveWorktreeOpenInTabBlocked`. Module-level imports go at the top of the file, not inside `flow`, if that matches the file's style.)

- [ ] **Step 4: Register.** Extend the `tasks/__init__.py` worktreetasks block (alphabetized):

```python
from gitfourchette.tasks.worktreetasks import (
    NewWorktree,
    PruneWorktrees,
    RemoveWorktree,
)
```

`TaskBook.names` at alphabetical slots:

```python
            tasks.PruneWorktrees: _("Prune worktrees"),
            tasks.RemoveWorktree: _("Remove worktree"),
```

- [ ] **Step 5: Menu entries** in `gitfourchette/sidebar/sidebar.py`:

WorktreesHeader case becomes:

```python
        elif item == SidebarItem.WorktreesHeader:
            actions += [
                TaskBook.action(self, NewWorktree, accel="N"),
                ActionDef.SEPARATOR,
                TaskBook.action(self, PruneWorktrees, accel="P"),
            ]
```

Worktree leaf case — append:

```python
                ActionDef.SEPARATOR,
                TaskBook.action(self, RemoveWorktree, accel="R", taskArgs=data),
```

(Mnemonic check within each menu: header menu N/P unique; leaf menu O/F/P(copy &Path)/R — `Copy &Path` already claims P, so `RemoveWorktree` must NOT auto-accel to P; `accel="R"` yields `&Remove worktree…` — verify the rendered mnemonics are unique, adjust accel letters if TaskBook's auto-accel collides.)

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -v`
Expected: 19 passed.

- [ ] **Step 7: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1040 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tasks/worktreetasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/sidebar/sidebar.py test/test_worktrees.py
git commit -m "feat: RemoveWorktree (with dirty force-retry) and PruneWorktrees tasks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## After all tasks

- Final whole-branch review (superpowers:requesting-code-review) on the most capable model, fed the Minor-findings roll-up from task reviews. Special attention: sidebar enum-tail convention, upstream-merge cleanliness of the sidebar/taskbook churn, `git worktree` process spawn per refresh (one `runSync` under `Refs|Head` — same cost class as the existing `for-each-ref` call), and interplay with the tab-colors feature (`repoHasLinkedWorktrees` in tabcolors.py stays independent by design — do NOT unify it with worktrees.py in this phase; note it as a possible future cleanup).
- Merge flow: merge `fork-main` into the branch, combined suite in the worktree, `git merge --ff-only` in the main checkout when clean.
- Manual GUI smoke (user): section look on the real repo (main + multiselect worktree listed), bold current worktree, New Worktree dialog feel, checkout-in-new-worktree from a branch, remove + force-remove flows, prune, Breeze icons.
