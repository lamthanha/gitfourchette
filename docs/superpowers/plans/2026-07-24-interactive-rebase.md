# Interactive Rebase (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Fork-style interactive rebase: right-click a commit → "Interactive Rebase from Here…" → a todo dialog (reorder / pick / drop / squash / fixup / reword) → the real `git rebase -i` executes the edited todo via helper-script editors, with conflicts falling back to the Phase 1 banner. Also clears the Phase 1 review backlog (banner label fallback, up-to-date status, pause wording, missing tests).

**Architecture:** A new pure-Python todo model (`gitfourchette/rebasetodo.py`, no Qt) handles validation, todo-file serialization, and editor-invocation planning. A new hand-coded dialog (`gitfourchette/forms/rebasetododialog.py`, QTreeWidget flat table with drag-and-drop) edits the todo. A new `InteractiveRebase` task in the existing `gitfourchette/tasks/rebasetasks.py` drives `git rebase --interactive` through `flowCallGit`, injecting `GIT_SEQUENCE_EDITOR`/`GIT_EDITOR` helper scripts generated in a per-invocation temp dir. Conflicts reuse the Phase 1 banner and ConflictView untouched.

**Tech Stack:** Python ≥3.10, PyQt6, pygit2 (reads only), pytest + pytest-qt, real `git` binary via GitDriver.

## Global Constraints

- Repo: `/home/admin/workspace.personal/gitfourchette`, branch `fork-main`. Spec: `docs/superpowers/specs/2026-07-24-gitfourchette-fork-design.md` (Phase 2 section).
- All commands run from the repo root. Test runner exists from Phase 1: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` (use this prefix for every pytest run).
- Every user-facing string goes through `_("...")` / `_n("...", "...", n=…)` from `gitfourchette.localization` (star-imported). Typographic characters in UI strings: `…` for ellipsis, `’` for apostrophe.
- New files start with the fork's standard 5-line header (exactly as in `gitfourchette/tasks/rebasetasks.py` lines 1–5: `Copyright (C) 2026 GitFourchette contributors.`).
- New task classes MUST be registered in `gitfourchette/tasks/__init__.py` AND `TaskBook.names` in `gitfourchette/tasks/taskbook.py`. Both the `names` and `tips` dicts are sorted alphabetically **by label text** — insert new entries at the label-alphabetical position. No `TaskBook.icons` entries.
- `env` dicts passed to `flowCallGit` are **overlaid onto the full system environment** key-by-key (`ToolCommands.setQProcessEnvironment`), so setting only `GIT_SEQUENCE_EDITOR`/`GIT_EDITOR` is safe.
- Editor rule: every plain `git rebase` invocation keeps `GIT_EDITOR=true` via `env=dict(GIT_NO_EDITOR)`. **Exception authorized by the spec (Phase 2):** `InteractiveRebase` sets `GIT_SEQUENCE_EDITOR` and `GIT_EDITOR` to generated helper scripts — these are non-interactive (they exit without waiting for input), which is the intent of the rule.
- Graph single-commit context menu mnemonics already in use (`graphview.py:467-486`): `&B` `&T` `&C` `&M` `&R` `&o` `&P` `&v` `&x` `&H` `&e` `&I` (+ `G`, and pre-existing `&M` collision with Mount). The new entry uses **`&a`**: `_("Interactive Reb&ase from Here…")`.
- pygit2 is for reads only; the rebase itself always runs the real git binary.
- `Branch.is_checked_out()` is worktree-wide — never use it to mean "is the current branch".
- TDD: failing test first, then implementation. Commit after each task with trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Phase 1 review-backlog polish

Clears the deferred findings recorded in `.superpowers/sdd/progress.md`: detached-HEAD banner label, misleading "Rebased X onto Y" status when the rebase was a no-op, misleading "resolve conflicts" status when a rebase pauses without conflicts, and two missing tests (autostash-unchecked error path, disabled sidebar entry).

**Files:**
- Modify: `gitfourchette/tasks/rebasetasks.py` (`rebaseProgress` ~line 107; `_flowRebaseGit` ~line 159; `RebaseOnto.flow` ~line 80)
- Test: `test/test_tasks_rebase.py` (append)

**Interfaces:**
- Consumes: existing `makeDivergentBranches(tempDir)`, `REBASE_STATES_FOR_TESTS`, `_bannerButton` from `test/test_tasks_rebase.py`; `findQMessageBox`, `findMenuAction` from `test/util.py`.
- Produces: `_flowRebaseGit(task, *args, successStatus: str, upToDateStatus: str = "")` — new keyword arg, empty means "always use successStatus". Task 4 extends this signature again (adds `env`); the two changes are independent keywords.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_tasks_rebase.py`:

```python
def testRebaseBannerDetachedHead(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    runShellScript(
        """
        git switch --detach feature
        git rebase master || true
        """,
        wd)
    rw = mainWindow.openRepo(wd)

    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.mergeBanner.isVisibleTo(rw)
    labelText = rw.mergeBanner.label.text()
    assert re.search(r"rebasing", labelText, re.I)
    # rebase-merge/head-name contains "detached HEAD" -- must not leak into the title
    assert not re.search(r"detached", labelText, re.I)


def testRebaseOntoAncestorIsUpToDate(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c feature master
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        """,
        wd)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target
    oldTip = rw.repo.branches.local["feature"].target

    rw.jump(NavLocator.inCommit(masterTip))
    # Clean tree, ahead of master: rebases immediately -- git reports "up to date"
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["feature"].target == oldTip
    assert re.search(r"up to date", mainWindow.statusBar().currentMessage(), re.I)


def testRebaseDirtyAutostashUnchecked(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch master
        echo "notes" > notes.txt
        git add notes.txt
        git commit -m "base: notes"
        git switch -c feature
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        git switch master
        echo "master only" > master.txt
        git add master.txt
        git commit -m "master: own file"
        git switch feature
        echo "notes dirty" > notes.txt
        """,
        wd)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target
    oldTip = rw.repo.branches.local["feature"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    qmb = findQMessageBox(rw, r"rebase.+feature.+onto")
    qmb.checkBox().setChecked(False)  # decline autostash
    qmb.accept()

    # git refuses to rebase a dirty tree without autostash; error is surfaced
    acceptQMessageBox(rw, r"unstaged|uncommitted|cannot")
    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["feature"].target == oldTip
    assert readFile(f"{wd}/notes.txt").decode() == "notes dirty\n"


def testRebaseSidebarEntryDisabledForCurrentBranch(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/feature")  # the checked-out branch
    menu = rw.sidebar.makeNodeMenu(node)
    action = findMenuAction(menu, r"rebase.+onto")
    assert not action.isEnabled()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py -x -q -k "DetachedHead or AncestorIsUpToDate or AutostashUnchecked or DisabledForCurrentBranch"`
Expected: `testRebaseBannerDetachedHead` FAILs (banner title contains "detached"); `testRebaseOntoAncestorIsUpToDate` FAILs (status says "Rebased feature onto…" not "up to date"). The other two may already pass (they test existing behavior with new coverage) — that's fine; they guard regressions.

Note: `mainWindow.statusBar().currentMessage()` is how `test/test_diff.py:90` asserts a task's status message. If the assertion fails *mechanically* (empty message despite the fix), find where `epilog.status` is routed (grep for `epilog.status` consumers in `repowidget.py`/`mainwindow.py`) and assert on that surface instead — do not drop the assertion.

- [ ] **Step 3: Fix `rebaseProgress` branch-name fallback**

In `gitfourchette/tasks/rebasetasks.py`, inside `rebaseProgress`, replace:

```python
            headName = read("head-name")
            branch = RefPrefix.split(headName)[1] if headName else ""
            return step, total, branch
```

with:

```python
            headName = read("head-name")
            branch = ""
            if headName.startswith("refs/"):
                branch = RefPrefix.split(headName)[1]
            return step, total, branch
```

(During a detached-HEAD rebase, git writes the literal string `detached HEAD` to `head-name`; the banner must fall back to the branch-less "Rebasing" title.)

- [ ] **Step 4: Fix `_flowRebaseGit` statuses**

Replace the whole `_flowRebaseGit` function with:

```python
def _flowRebaseGit(task: RepoTask, *args: str, successStatus: str, upToDateStatus: str = ""):
    """Run a git rebase command and resolve its outcome. Shared by every
    rebase task; call with `yield from`. A nonzero exit is only an error if
    the repo did NOT end up in (or remain in) a rebase state — otherwise the
    rebase merely paused and the banner takes over."""
    task.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
    oldHead = task.repo.head_commit_id
    driver = yield from task.flowCallGit(*args, env=dict(GIT_NO_EDITOR), autoFail=False)

    yield from task.flowEnterWorkerThread()
    task.repo.refresh_index()
    stillRebasing = task.repo.state() in REBASE_STATES
    anyConflicts = task.repo.any_conflicts
    yield from task.flowEnterUiThread()

    if driver.exitCode() != 0 and not stillRebasing:
        raise AbortTask(driver.htmlErrorText())
    if stillRebasing:
        if anyConflicts:
            task.epilog.status = _("Rebase interrupted: resolve conflicts, then continue the rebase.")
        else:
            task.epilog.status = _("Rebase paused. Use the banner to continue, skip, or abort.")
        task.epilog.jumpTo = NavLocator.inWorkdir()
    elif anyConflicts:
        task.epilog.status = _("Rebase succeeded, but reapplying your stashed changes caused conflicts.")
        task.epilog.jumpTo = NavLocator.inWorkdir()
    elif upToDateStatus and task.repo.head_commit_id == oldHead:
        task.epilog.status = upToDateStatus
    else:
        task.epilog.status = successStatus
```

(The non-conflict pause wording has no dedicated test: reaching it requires a hook failure or an `edit` todo action, neither of which this fork can produce. The conflict wording stays covered by existing tests.)

- [ ] **Step 5: Pass `upToDateStatus` from `RebaseOnto`**

In `RebaseOnto.flow`, change the final call to:

```python
        yield from _flowRebaseGit(
            self,
            "rebase", *argsIf(autostash, "--autostash"), str(ontoId),
            successStatus=_("Rebased {0} onto {1}.", tquo(branchName), tquo(ontoDisplay)),
            upToDateStatus=_("{0} is already up to date with {1}.", tquo(branchName), tquo(ontoDisplay)))
```

- [ ] **Step 6: Run the rebase suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py -q`
Expected: all PASS (existing Phase 1 tests must not regress).

- [ ] **Step 7: Commit**

```bash
git add gitfourchette/tasks/rebasetasks.py test/test_tasks_rebase.py
git commit -m "fix: rebase polish from Phase 1 review backlog

Detached-HEAD banner title fallback, honest up-to-date status,
non-conflict pause wording; cover autostash-unchecked error path
and disabled sidebar entry.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Pure todo model — `gitfourchette/rebasetodo.py`

Qt-free model shared by the dialog (Task 3) and the task (Task 4): row dataclass, validation, todo-file serialization, and the plan of editor invocations git will make.

**Files:**
- Create: `gitfourchette/rebasetodo.py`
- Create: `test/test_rebasetodo.py`

**Interfaces:**
- Consumes: only `gitfourchette.localization` (star import; safe without a running app — `gitfourchette/porcelain.py` does the same).
- Produces (exact names used by Tasks 3–5):
  - `TODO_ACTIONS: tuple[str, ...] = ("pick", "reword", "squash", "fixup", "drop")`
  - `@dataclass class RebaseTodoRow: oid: str; summary: str; author: str = ""; fullMessage: str = ""; action: str = "pick"; message: str = ""` (`oid` is the full 40-char hex string; `message` is the user's replacement/combined message, `""` = not customized)
  - `validateTodo(rowsOldestFirst: list[RebaseTodoRow]) -> str` — error message, `""` if executable
  - `formatTodoFile(rowsOldestFirst: list[RebaseTodoRow]) -> str` — git todo file content (explicit `drop` lines)
  - `planEditorMessages(rowsOldestFirst: list[RebaseTodoRow]) -> list[str]` — one entry per editor invocation git will make, in order; `""` = leave git's default message untouched
  - `combinedSquashMessage(rowsOldestFirst: list[RebaseTodoRow], index: int) -> str` — pre-fill text for a squash row's chain

- [ ] **Step 1: Write the failing tests**

Create `test/test_rebasetodo.py`:

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""Pure unit tests for the interactive-rebase todo model (no Qt, no repo)."""

from gitfourchette.rebasetodo import (
    RebaseTodoRow,
    TODO_ACTIONS,
    combinedSquashMessage,
    formatTodoFile,
    planEditorMessages,
    validateTodo,
)


def row(oid, summary, action="pick", message="", fullMessage=""):
    return RebaseTodoRow(oid=oid * 40, summary=summary, action=action,
                         message=message, fullMessage=fullMessage or summary + "\n")


def testActionsTuple():
    assert TODO_ACTIONS == ("pick", "reword", "squash", "fixup", "drop")


def testValidateHappyPath():
    rows = [row("a", "one"), row("b", "two", "squash", message="combined"),
            row("c", "three", "fixup"), row("d", "four", "drop")]
    assert validateTodo(rows) == ""


def testValidateFirstKeptCannotBeSquashOrFixup():
    for bad in ("squash", "fixup"):
        assert validateTodo([row("a", "one", bad), row("b", "two")]) != ""
        # Leading drops don't count as a fold target either
        assert validateTodo([row("a", "one", "drop"), row("b", "two", bad),
                             row("c", "three")]) != ""


def testValidateAllDropped():
    assert validateTodo([row("a", "one", "drop"), row("b", "two", "drop")]) != ""


def testValidateRewordNeedsMessage():
    assert validateTodo([row("a", "one", "reword", message="  ")]) != ""
    assert validateTodo([row("a", "one", "reword", message="new msg")]) == ""


def testFormatTodoFile():
    rows = [row("a", "one"), row("b", "two", "drop"), row("c", "three", "reword", message="x")]
    assert formatTodoFile(rows) == (
        f"pick {'a' * 40} one\n"
        f"drop {'b' * 40} two\n"
        f"reword {'c' * 40} three\n")


def testPlanNoEditorForPicksAndFixups():
    rows = [row("a", "one"), row("b", "two", "fixup"), row("c", "three")]
    assert planEditorMessages(rows) == []


def testPlanRewordThenSquashChain():
    # Execution order: pick a; reword b (editor #1); squash c (editor #2)
    rows = [row("a", "one"),
            row("b", "two", "reword", message="two, reworded"),
            row("c", "three", "squash", message="two+three combined")]
    assert planEditorMessages(rows) == ["two, reworded", "two+three combined"]


def testPlanSquashChainLastEditedMessageWins():
    rows = [row("a", "one"),
            row("b", "two", "squash"),
            row("c", "three", "squash", message="final message")]
    assert planEditorMessages(rows) == ["final message"]


def testPlanUneditedSquashLeavesGitDefault():
    rows = [row("a", "one"), row("b", "two", "squash")]
    assert planEditorMessages(rows) == [""]


def testPlanTwoSeparateChains():
    rows = [row("a", "one"), row("b", "two", "squash", message="first chain"),
            row("c", "three"), row("d", "four", "squash", message="second chain")]
    assert planEditorMessages(rows) == ["first chain", "second chain"]


def testCombinedSquashMessage():
    rows = [row("a", "one", fullMessage="one\n\nbody one\n"),
            row("b", "two", "squash", fullMessage="two\n"),
            row("c", "three", "fixup", fullMessage="three\n"),
            row("d", "four", "squash", fullMessage="four\n")]
    combined = combinedSquashMessage(rows, 1)
    assert "one\n\nbody one" in combined
    assert "two" in combined
    assert "four" in combined
    assert "three" not in combined  # fixup messages are discarded by git
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_rebasetodo.py -x -q`
Expected: FAIL at import — `No module named 'gitfourchette.rebasetodo'`.

- [ ] **Step 3: Create `gitfourchette/rebasetodo.py`**

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""Pure-Python model for an interactive-rebase todo list.

No Qt and no pygit2 in here: rows carry plain strings so the model can be
unit-tested without an app or a repository. Rows are always handled in git's
execution order (oldest first) at this layer; the dialog is responsible for
flipping its newest-first display order before calling in.
"""

from dataclasses import dataclass

from gitfourchette.localization import *

TODO_ACTIONS = ("pick", "reword", "squash", "fixup", "drop")

_FOLD_ACTIONS = ("squash", "fixup")


@dataclass
class RebaseTodoRow:
    oid: str
    """Full hex hash of the commit."""

    summary: str
    """First line of the original commit message."""

    author: str = ""

    fullMessage: str = ""
    """Complete original commit message (pre-fill for reword/squash editing)."""

    action: str = "pick"

    message: str = ""
    """User-provided replacement message (reword) or combined message for the
    squash chain this row belongs to. Empty = keep git's default."""


def validateTodo(rowsOldestFirst: list[RebaseTodoRow]) -> str:
    """Return an error message, or an empty string if the todo is executable."""
    anyKept = False
    for row in rowsOldestFirst:
        if row.action == "drop":
            continue
        if row.action in _FOLD_ACTIONS and not anyKept:
            return _("The first commit to be replayed can’t be squashed or fixed up — "
                     "there’s no earlier commit to fold it into.")
        if row.action == "reword" and not row.message.strip():
            return _("Enter a new message for the reworded commit.")
        anyKept = True
    if not anyKept:
        return _("Every commit is dropped — there’s nothing left to do.")
    return ""


def formatTodoFile(rowsOldestFirst: list[RebaseTodoRow]) -> str:
    """Serialize the rows to git's todo-file format (oldest first).
    Dropped commits get explicit 'drop' lines so git never warns about
    silently-missing commits regardless of rebase.missingCommitsCheck."""
    lines = [f"{row.action} {row.oid} {row.summary}".rstrip() for row in rowsOldestFirst]
    return "\n".join(lines) + "\n"


def planEditorMessages(rowsOldestFirst: list[RebaseTodoRow]) -> list[str]:
    """Predict the sequence of editor invocations `git rebase -i` will make
    for this todo, and the message to substitute at each one ('' = accept
    git's default). git opens the editor once per reword (when that commit is
    applied) and once per squash chain (after the chain's last fold);
    fixup-only chains open no editor."""
    invocations = []
    chainHasSquash = False
    chainMessage = ""
    for row in rowsOldestFirst:
        if row.action == "drop":
            continue
        if row.action in _FOLD_ACTIONS:
            if row.action == "squash":
                chainHasSquash = True
                if row.message:
                    chainMessage = row.message
            continue
        # pick or reword: closes any open fold chain
        if chainHasSquash:
            invocations.append(chainMessage)
        chainHasSquash = False
        chainMessage = ""
        if row.action == "reword":
            invocations.append(row.message)
    if chainHasSquash:
        invocations.append(chainMessage)
    return invocations


def combinedSquashMessage(rowsOldestFirst: list[RebaseTodoRow], index: int) -> str:
    """Concatenated messages of the squash chain containing rowsOldestFirst[index]:
    the anchor commit's message plus every squash member's (fixup messages are
    discarded by git). Used to pre-fill the message editor for a squash row."""
    kept = [row for row in rowsOldestFirst if row.action != "drop"]
    target = rowsOldestFirst[index]
    if target not in kept:
        return ""
    anchor = kept.index(target)
    while anchor > 0 and kept[anchor].action in _FOLD_ACTIONS:
        anchor -= 1
    parts = [kept[anchor].fullMessage]
    walk = anchor + 1
    while walk < len(kept) and kept[walk].action in _FOLD_ACTIONS:
        if kept[walk].action == "squash":
            parts.append(kept[walk].fullMessage)
        walk += 1
    return "\n\n".join(part.strip() for part in parts if part.strip()) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_rebasetodo.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/rebasetodo.py test/test_rebasetodo.py
git commit -m "feat: pure todo model for interactive rebase

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `RebaseTodoDialog`

Hand-coded QDialog (no `.ui` file — precedent: `gitfourchette/forms/textinputdialog.py`). Flat QTreeWidget as the todo table: newest commit at top (matching the graph), drag-and-drop row reordering (QTreeWidget's InternalMove moves the real items, unlike QTableWidget), combo-box editing of the Action column via a delegate, context menu + programmatic API for multi-row action changes, an inline message editor for reword/squash rows, live validation gating the OK button, plus a merge-flattening warning and an optional autostash checkbox.

**Files:**
- Create: `gitfourchette/forms/rebasetododialog.py`
- Create: `test/test_rebasetododialog.py`

**Interfaces:**
- Consumes: `TODO_ACTIONS`, `RebaseTodoRow`, `validateTodo`, `combinedSquashMessage` from `gitfourchette.rebasetodo` (Task 2).
- Produces (exact API used by Tasks 4–5):
  - `RebaseTodoDialog(rowsNewestFirst: list[RebaseTodoRow], flattenedMerges: int, offerAutostash: bool, parent=None)`
  - `.rows() -> list[RebaseTodoRow]` — display order (newest first), reflecting reorders
  - `.executionRows() -> list[RebaseTodoRow]` — `list(reversed(rows()))`
  - `.setAction(index: int, action: str)` — display index; setting `"reword"` auto-fills `row.message` with `row.fullMessage` if empty
  - `.setMessage(index: int, message: str)` — display index; row must be reword/squash
  - `.moveRow(fromIndex: int, toIndex: int)` — display indices
  - `.setActionForSelection(action: str)` — applies to all selected rows
  - `.autostash() -> bool` — False whenever `offerAutostash` was False
  - Attributes tests touch: `.table` (QTreeWidget), `.messageEdit` (QPlainTextEdit), `.errorLabel`, `.mergeWarningLabel`, `.autostashCheckBox`, `.okButton`
  - Window title contains "Interactive Rebase" (how `findQDialog` locates it)

- [ ] **Step 1: Write the failing tests**

Create `test/test_rebasetododialog.py`:

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""Widget-level tests for RebaseTodoDialog, constructed directly (no repo).
The mainWindow fixture is only used to bootstrap the QApplication."""

import re

from gitfourchette.forms.rebasetododialog import RebaseTodoDialog
from gitfourchette.rebasetodo import RebaseTodoRow, planEditorMessages
from .util import *


def _rows():
    # Display order: newest first ("three" is HEAD)
    return [
        RebaseTodoRow(oid="c" * 40, summary="ir: three", author="Alice",
                      fullMessage="ir: three\n\nbody three\n"),
        RebaseTodoRow(oid="b" * 40, summary="ir: two", author="Bob",
                      fullMessage="ir: two\n"),
        RebaseTodoRow(oid="a" * 40, summary="ir: one", author="Alice",
                      fullMessage="ir: one\n"),
    ]


def _dialog(mainWindow, rows=None, flattenedMerges=0, offerAutostash=False):
    dlg = RebaseTodoDialog(rows or _rows(), flattenedMerges, offerAutostash, None)
    return dlg


def testTodoDialogDefaults(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    assert re.search(r"interactive rebase", dlg.windowTitle(), re.I)
    assert [r.summary for r in dlg.rows()] == ["ir: three", "ir: two", "ir: one"]
    assert [r.summary for r in dlg.executionRows()] == ["ir: one", "ir: two", "ir: three"]
    assert all(r.action == "pick" for r in dlg.rows())
    assert dlg.okButton.isEnabled()
    assert not dlg.errorLabel.isVisibleTo(dlg)
    assert not dlg.mergeWarningLabel.isVisibleTo(dlg)
    assert not dlg.autostashCheckBox.isVisibleTo(dlg)
    assert not dlg.autostash()
    dlg.deleteLater()


def testTodoDialogValidationGatesOkButton(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    # Display index 2 == oldest == first executed: cannot be squashed
    dlg.setAction(2, "squash")
    assert not dlg.okButton.isEnabled()
    assert dlg.errorLabel.isVisibleTo(dlg)
    dlg.setAction(2, "pick")
    assert dlg.okButton.isEnabled()
    assert not dlg.errorLabel.isVisibleTo(dlg)
    dlg.deleteLater()


def testTodoDialogAllDroppedDisablesOk(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    for i in range(3):
        dlg.setAction(i, "drop")
    assert not dlg.okButton.isEnabled()
    dlg.setAction(0, "pick")
    assert dlg.okButton.isEnabled()
    dlg.deleteLater()


def testTodoDialogMoveRow(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.moveRow(0, 1)  # "three" below "two"
    assert [r.summary for r in dlg.rows()] == ["ir: two", "ir: three", "ir: one"]
    assert [r.summary for r in dlg.executionRows()] == ["ir: one", "ir: three", "ir: two"]
    dlg.deleteLater()


def testTodoDialogRewordPrefillsMessage(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.setAction(1, "reword")
    assert dlg.rows()[1].message == "ir: two\n"
    dlg.table.setCurrentItem(dlg.table.topLevelItem(1))
    assert dlg.messageEdit.isEnabled()
    assert dlg.messageEdit.toPlainText() == "ir: two\n"
    dlg.setMessage(1, "ir: two, reworded")
    assert dlg.rows()[1].message == "ir: two, reworded"
    dlg.deleteLater()


def testTodoDialogSquashPrefillsCombinedMessage(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.setAction(1, "squash")  # "two" folds into "one"
    dlg.table.setCurrentItem(dlg.table.topLevelItem(1))
    assert dlg.messageEdit.isEnabled()
    preview = dlg.messageEdit.toPlainText()
    assert "ir: one" in preview
    assert "ir: two" in preview
    dlg.setMessage(1, "one and two combined")
    assert planEditorMessages(dlg.executionRows()) == ["one and two combined"]
    dlg.deleteLater()


def testTodoDialogMessageEditorDisabledForPick(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))
    assert not dlg.messageEdit.isEnabled()
    dlg.deleteLater()


def testTodoDialogMultiSelectSetAction(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.table.topLevelItem(0).setSelected(True)
    dlg.table.topLevelItem(1).setSelected(True)
    dlg.setActionForSelection("drop")
    assert [r.action for r in dlg.rows()] == ["drop", "drop", "pick"]
    assert dlg.okButton.isEnabled()  # one pick left, and it needs no fold target
    dlg.deleteLater()


def testTodoDialogAutostashCheckbox(tempDir, mainWindow):
    dlg = _dialog(mainWindow, offerAutostash=True)
    assert dlg.autostashCheckBox.isVisibleTo(dlg)
    assert dlg.autostash()
    dlg.autostashCheckBox.setChecked(False)
    assert not dlg.autostash()
    dlg.deleteLater()


def testTodoDialogMergeWarning(tempDir, mainWindow):
    dlg = _dialog(mainWindow, flattenedMerges=2)
    assert dlg.mergeWarningLabel.isVisibleTo(dlg)
    dlg.deleteLater()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_rebasetododialog.py -x -q`
Expected: FAIL at import — `No module named 'gitfourchette.forms.rebasetododialog'`.

- [ ] **Step 3: Create `gitfourchette/forms/rebasetododialog.py`**

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.rebasetodo import (
    TODO_ACTIONS,
    RebaseTodoRow,
    combinedSquashMessage,
    validateTodo,
)
from gitfourchette.toolbox import *

_ROW_ROLE = Qt.ItemDataRole.UserRole


class _ActionDelegate(QStyledItemDelegate):
    """Combo-box editor for the Action column; other columns aren't editable."""

    def createEditor(self, parent, option, index):
        if index.column() != 0:
            return None
        combo = QComboBox(parent)
        combo.addItems(list(TODO_ACTIONS))
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentText(index.data() or "pick")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText())


class _TodoTable(QTreeWidget):
    """Flat tree widget: InternalMove drag-and-drop moves whole rows without
    destroying the items (QTableWidget can't do this cleanly)."""

    def __init__(self, dialog: "RebaseTodoDialog"):
        super().__init__(dialog)
        self._dialog = dialog

    def dropEvent(self, event):
        super().dropEvent(event)
        self._dialog._refreshMessageEditor()
        self._dialog._revalidate()


class RebaseTodoDialog(QDialog):
    def __init__(self, rowsNewestFirst: list[RebaseTodoRow], flattenedMerges: int,
                 offerAutostash: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("RebaseTodoDialog")
        self.setWindowTitle(_("Interactive Rebase"))
        self.setModal(True)
        self._offerAutostash = offerAutostash

        self.hintLabel = QLabel(
            _("Commits are listed newest first, like the graph. "
              "Git replays them bottom-up: the bottom row executes first."), self)
        self.hintLabel.setWordWrap(True)

        self.mergeWarningLabel = QLabel(
            _n("This range contains {n} merge commit. Git flattens merges during "
               "an interactive rebase: the merge itself disappears and the merged "
               "commits are replayed in a straight line.",
               "This range contains {n} merge commits. Git flattens merges during "
               "an interactive rebase: the merges themselves disappear and the merged "
               "commits are replayed in a straight line.",
               n=flattenedMerges), self)
        self.mergeWarningLabel.setWordWrap(True)
        self.mergeWarningLabel.setVisible(flattenedMerges > 0)

        self.table = _TodoTable(self)
        self.table.setColumnCount(4)
        self.table.setHeaderLabels([_("Action"), _("Commit"), _("Summary"), _("Author")])
        self.table.setRootIsDecorated(False)
        self.table.setAllColumnsShowFocus(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setItemDelegate(_ActionDelegate(self.table))
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._onContextMenu)
        self.table.itemChanged.connect(self._onItemChanged)
        self.table.currentItemChanged.connect(lambda *_a: self._refreshMessageEditor())

        for row in rowsNewestFirst:
            self._makeItem(row)
        header = self.table.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.moveUpButton = QPushButton(_("Move &Up"), self)
        self.moveUpButton.clicked.connect(lambda: self._moveCurrent(-1))
        self.moveDownButton = QPushButton(_("Move &Down"), self)
        self.moveDownButton.clicked.connect(lambda: self._moveCurrent(+1))

        self.messageEdit = QPlainTextEdit(self)
        self.messageEdit.setPlaceholderText(
            _("Select a reworded or squashed row to edit its message."))
        self.messageEdit.setEnabled(False)
        self.messageEdit.textChanged.connect(self._onMessageEdited)

        self.autostashCheckBox = QCheckBox(
            _("Autostash (stash uncommitted changes, then reapply them)"), self)
        self.autostashCheckBox.setChecked(True)
        self.autostashCheckBox.setVisible(offerAutostash)

        self.errorLabel = QLabel(self)
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setVisible(False)

        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.okButton = self.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.okButton.setText(_("&Start Rebase"))

        moveButtons = QHBoxLayout()
        moveButtons.addWidget(self.moveUpButton)
        moveButtons.addWidget(self.moveDownButton)
        moveButtons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.hintLabel)
        layout.addWidget(self.mergeWarningLabel)
        layout.addWidget(self.table, stretch=3)
        layout.addLayout(moveButtons)
        layout.addWidget(QLabel(_("Message (for reword and squash):"), self))
        layout.addWidget(self.messageEdit, stretch=1)
        layout.addWidget(self.autostashCheckBox)
        layout.addWidget(self.errorLabel)
        layout.addWidget(self.buttonBox)
        self.resize(640, 480)

        if self.table.topLevelItemCount():
            self.table.setCurrentItem(self.table.topLevelItem(0))
        self._refreshMessageEditor()
        self._revalidate()

    # ------------------------------------------------------------------------
    # Item plumbing

    def _makeItem(self, row: RebaseTodoRow):
        item = QTreeWidgetItem([row.action, row.oid[:7], row.summary, row.author])
        item.setData(0, _ROW_ROLE, row)
        # NOT ItemIsDropEnabled: forbids dropping ONTO a row (which would nest it)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsDragEnabled)
        self.table.addTopLevelItem(item)

    def _onItemChanged(self, item: QTreeWidgetItem, column: int):
        if column != 0:
            return
        row = item.data(0, _ROW_ROLE)
        action = item.text(0)
        if action not in TODO_ACTIONS:  # reject bogus edits
            with QSignalBlocker(self.table):
                item.setText(0, row.action)
            return
        self._applyAction(row, item, action)

    def _applyAction(self, row: RebaseTodoRow, item: QTreeWidgetItem, action: str):
        row.action = action
        if action == "reword" and not row.message:
            row.message = row.fullMessage
        with QSignalBlocker(self.table):
            item.setText(0, action)
        self._refreshMessageEditor()
        self._revalidate()

    def _onContextMenu(self, point):
        menu = QMenu(self.table)
        for action in TODO_ACTIONS:
            menu.addAction(action, lambda a=action: self.setActionForSelection(a))
        menu.exec(self.table.viewport().mapToGlobal(point))
        menu.deleteLater()

    def _moveCurrent(self, delta: int):
        item = self.table.currentItem()
        if item is None:
            return
        i = self.table.indexOfTopLevelItem(item)
        j = i + delta
        if 0 <= j < self.table.topLevelItemCount():
            self.moveRow(i, j)

    def _refreshMessageEditor(self):
        item = self.table.currentItem()
        row = item.data(0, _ROW_ROLE) if item is not None else None
        editable = row is not None and row.action in ("reword", "squash")
        self.messageEdit.setEnabled(editable)
        with QSignalBlocker(self.messageEdit):
            if not editable:
                self.messageEdit.setPlainText("")
            elif row.message:
                self.messageEdit.setPlainText(row.message)
            elif row.action == "squash":
                execRows = self.executionRows()
                self.messageEdit.setPlainText(
                    combinedSquashMessage(execRows, execRows.index(row)))
            else:
                self.messageEdit.setPlainText(row.fullMessage)

    def _onMessageEdited(self):
        item = self.table.currentItem()
        if item is None or not self.messageEdit.isEnabled():
            return
        row = item.data(0, _ROW_ROLE)
        row.message = self.messageEdit.toPlainText()
        self._revalidate()

    def _revalidate(self):
        error = validateTodo(self.executionRows())
        self.errorLabel.setText(error)
        self.errorLabel.setVisible(bool(error))
        self.okButton.setEnabled(not error)

    # ------------------------------------------------------------------------
    # Public API (used by InteractiveRebase and by tests)

    def rows(self) -> list[RebaseTodoRow]:
        return [self.table.topLevelItem(i).data(0, _ROW_ROLE)
                for i in range(self.table.topLevelItemCount())]

    def executionRows(self) -> list[RebaseTodoRow]:
        return list(reversed(self.rows()))

    def setAction(self, index: int, action: str):
        assert action in TODO_ACTIONS
        item = self.table.topLevelItem(index)
        self._applyAction(item.data(0, _ROW_ROLE), item, action)

    def setMessage(self, index: int, message: str):
        row = self.table.topLevelItem(index).data(0, _ROW_ROLE)
        assert row.action in ("reword", "squash")
        row.message = message
        self._refreshMessageEditor()
        self._revalidate()

    def setActionForSelection(self, action: str):
        assert action in TODO_ACTIONS
        for item in self.table.selectedItems():
            self._applyAction(item.data(0, _ROW_ROLE), item, action)

    def moveRow(self, fromIndex: int, toIndex: int):
        item = self.table.takeTopLevelItem(fromIndex)
        self.table.insertTopLevelItem(toIndex, item)
        self.table.setCurrentItem(item)
        self._refreshMessageEditor()
        self._revalidate()

    def autostash(self) -> bool:
        return self._offerAutostash and self.autostashCheckBox.isChecked()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_rebasetododialog.py -q`
Expected: all PASS. If `QSignalBlocker` or a Qt enum is missing from the star import, check `gitfourchette/qt.py` for the canonical name before adding imports.

- [ ] **Step 5: Run the model tests too (shared module)**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_rebasetodo.py test/test_rebasetododialog.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/forms/rebasetododialog.py test/test_rebasetododialog.py
git commit -m "feat: interactive rebase todo dialog

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `InteractiveRebase` task, helper scripts, menu entry — happy paths

**Files:**
- Modify: `gitfourchette/tasks/rebasetasks.py` (imports; `_flowRebaseGit` env param; new `_writeRebaseScripts`; new `InteractiveRebase`)
- Modify: `gitfourchette/tasks/__init__.py` (rebasetasks import block, lines 28–33)
- Modify: `gitfourchette/tasks/taskbook.py` (`names` + `tips` dicts, label-alphabetical)
- Modify: `gitfourchette/graphview/graphview.py` (task import; `_contextMenuActions1Commit`, insert after `RebaseOnto` at line ~474)
- Test: `test/test_tasks_rebase.py` (append)

**Interfaces:**
- Consumes: `RebaseTodoRow`, `formatTodoFile`, `planEditorMessages`, `validateTodo` (Task 2); `RebaseTodoDialog` with `.executionRows()`, `.autostash()` (Task 3); `_flowRebaseGit` with `upToDateStatus` (Task 1); `messageSummary` from toolbox (returns a `(summary, continued)` tuple); `SortMode` from porcelain.
- Produces: `class InteractiveRebase(RepoTask)` with `flow(self, fromCommit: Oid)`; `_flowRebaseGit(..., env: dict[str, str] | None = None)` (None → `dict(GIT_NO_EDITOR)`); `_writeRebaseScripts(payloadDir: str, todoText: str, editorMessages: list[str]) -> tuple[str, str]` returning (sequence-editor path, message-editor path); test helpers `makeLinearHistory(tempDir) -> str`, `_commitIdByMessage(repo, prefix) -> Oid`, `_logSummaries(repo, n) -> list[str]` in `test/test_tasks_rebase.py`. Task 5 relies on all of these.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_tasks_rebase.py`:

```python
def makeLinearHistory(tempDir) -> str:
    """Branch 'work' with three independent commits (each touches its own
    file), so any reordering replays cleanly. Newest commit: 'ir: three'."""
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c work master
        echo one > one.txt
        git add one.txt
        git commit -m "ir: one"
        echo two > two.txt
        git add two.txt
        git commit -m "ir: two"
        echo three > three.txt
        git add three.txt
        git commit -m "ir: three"
        """,
        wd)
    return wd


def _commitIdByMessage(repo, prefix: str):
    return next(c.id for c in repo.walk(repo.head_commit_id)
                if c.message.startswith(prefix))


def _logSummaries(repo, n: int) -> list[str]:
    summaries = []
    for commit in repo.walk(repo.head_commit_id):
        if len(summaries) == n:
            break
        summaries.append(commit.message.splitlines()[0])
    return summaries


def _openTodoDialog(rw, fromPrefix: str):
    fromId = _commitIdByMessage(rw.repo, fromPrefix)
    rw.jump(NavLocator.inCommit(fromId))
    triggerContextMenuAction(rw.graphView.viewport(), r"interactive rebase")
    return findQDialog(rw, r"interactive rebase")


def testInteractiveRebaseReorder(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    assert [r.summary for r in dlg.rows()] == ["ir: three", "ir: two", "ir: one"]
    assert not dlg.autostash()  # clean tree: no autostash offer
    dlg.moveRow(0, 1)  # "three" now executes before "two"
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 3) == ["ir: two", "ir: three", "ir: one"]
    headTree = rw.repo.peel_commit(rw.repo.head_commit_id).tree
    for name in ("one.txt", "two.txt", "three.txt"):
        assert name in headTree
    # Success jumps the view to the rebased HEAD
    assert rw.navLocator.commit == rw.repo.head_commit_id


def testInteractiveRebaseDrop(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "drop")  # drop "ir: two"
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: three", "ir: one"]
    headTree = rw.repo.peel_commit(rw.repo.head_commit_id).tree
    assert "two.txt" not in headTree
    assert "three.txt" in headTree


def testInteractiveRebaseSquashWithEditedMessage(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "squash")  # "ir: two" folds into "ir: one"
    dlg.setMessage(1, "ir: one and two combined\n\nSquashed by test.")
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: three", "ir: one and two combined"]
    combined = rw.repo.peel_commit(rw.repo.head_commit_id).parents[0]
    assert "Squashed by test." in combined.message
    assert "one.txt" in combined.tree
    assert "two.txt" in combined.tree


def testInteractiveRebaseFixup(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "fixup")  # "ir: two" melds into "ir: one", message discarded
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: three", "ir: one"]
    combined = rw.repo.peel_commit(rw.repo.head_commit_id).parents[0]
    assert "two.txt" in combined.tree


def testInteractiveRebaseReword(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.setAction(1, "reword")
    dlg.setMessage(1, "ir: two (reworded)\n\nMore detail.")
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 3) == ["ir: three", "ir: two (reworded)", "ir: one"]
    reworded = rw.repo.peel_commit(rw.repo.head_commit_id).parents[0]
    assert "More detail." in reworded.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py -x -q -k InteractiveRebase`
Expected: FAIL — `triggerContextMenuAction` raises because no menu item matches `interactive rebase`.

- [ ] **Step 3: Extend `gitfourchette/tasks/rebasetasks.py`**

Add to the imports at the top:

```python
import shlex
import shutil
import tempfile
from pathlib import Path

from gitfourchette.forms.rebasetododialog import RebaseTodoDialog
from gitfourchette.rebasetodo import (
    RebaseTodoRow,
    formatTodoFile,
    planEditorMessages,
    validateTodo,
)
```

Give `_flowRebaseGit` an `env` parameter — change its signature and the `flowCallGit` line:

```python
def _flowRebaseGit(task: RepoTask, *args: str, successStatus: str, upToDateStatus: str = "",
                   env: dict[str, str] | None = None):
```

```python
    if env is None:
        env = dict(GIT_NO_EDITOR)
    driver = yield from task.flowCallGit(*args, env=env, autoFail=False)
```

Add the script generator and the task (after `RebaseOnto`, before `rebaseProgress`):

```python
def _writeRebaseScripts(payloadDir: str, todoText: str, editorMessages: list[str]) -> tuple[str, str]:
    """Write the todo file, the queued editor messages, and two tiny shell
    scripts into payloadDir. Returns (sequenceEditorPath, messageEditorPath).

    The sequence editor overwrites git's generated todo with ours. The message
    editor pops msg-N.txt on git's Nth editor invocation (reword/squash
    prompts); when no payload file exists for an invocation, it leaves the file
    untouched so git's default message applies (graceful degradation, e.g.
    after a conflict pause when ContinueRebase runs with GIT_EDITOR=true)."""
    payload = Path(payloadDir)
    (payload / "todo.txt").write_text(todoText, "utf-8")
    for i, message in enumerate(editorMessages, start=1):
        if message:
            if not message.endswith("\n"):
                message += "\n"
            (payload / f"msg-{i}.txt").write_text(message, "utf-8")

    quotedPayload = shlex.quote(str(payload))

    sequenceEditor = payload / "sequence-editor.sh"
    sequenceEditor.write_text(
        "#!/bin/sh\n"
        f"cat {quotedPayload}/todo.txt > \"$1\"\n",
        "utf-8")
    sequenceEditor.chmod(0o700)

    messageEditor = payload / "message-editor.sh"
    messageEditor.write_text(
        "#!/bin/sh\n"
        f"dir={quotedPayload}\n"
        "n=$(cat \"$dir/counter\" 2>/dev/null || echo 0)\n"
        "n=$((n + 1))\n"
        "printf %s \"$n\" > \"$dir/counter\"\n"
        "if [ -f \"$dir/msg-$n.txt\" ]; then\n"
        "    cat \"$dir/msg-$n.txt\" > \"$1\"\n"
        "fi\n",
        "utf-8")
    messageEditor.chmod(0o700)

    return str(sequenceEditor), str(messageEditor)


class InteractiveRebase(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, fromCommit: Oid):
        repo = self.repo

        if repo.state() != RepositoryState.NONE:
            raise AbortTask(_("Conclude the ongoing operation before rebasing."))

        headId = repo.head_commit_id
        if fromCommit != headId and not repo.descendant_of(headId, fromCommit):
            raise AbortTask(_("To edit history from this commit, it must be an "
                              "ancestor of the current HEAD."))

        startCommit = repo.peel_commit(fromCommit)
        baseId = startCommit.parent_ids[0] if startCommit.parent_ids else None

        yield from self.flowEnterWorkerThread()
        rows = []
        flattenedMerges = 0
        walker = repo.walk(headId, SortMode.TOPOLOGICAL)
        if baseId is not None:
            walker.hide(baseId)
        for commit in walker:
            if len(commit.parent_ids) > 1:
                # git rebase -i omits merges from the todo (default flattening)
                flattenedMerges += 1
                continue
            rows.append(RebaseTodoRow(
                oid=str(commit.id),
                summary=messageSummary(commit.message)[0],
                author=commit.author.name,
                fullMessage=commit.message))
        repo.refresh_index()
        dirty = bool(repo.status(untracked_files="no"))
        yield from self.flowEnterUiThread()

        if not rows:
            raise AbortTask(_("There are no commits to edit in this range."),
                            icon="information")

        dlg = RebaseTodoDialog(rows, flattenedMerges, dirty, self.parentWidget())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        execRows = dlg.executionRows()
        autostash = dlg.autostash()
        assert not validateTodo(execRows), "dialog let an invalid todo through"

        payloadDir = tempfile.mkdtemp(prefix="gitfourchette-rebase-todo-")
        try:
            yield from self.flowEnterWorkerThread()
            sequenceEditor, messageEditor = _writeRebaseScripts(
                payloadDir, formatTodoFile(execRows), planEditorMessages(execRows))
            yield from self.flowEnterUiThread()

            env = dict(GIT_NO_EDITOR)
            env["GIT_SEQUENCE_EDITOR"] = shlex.quote(sequenceEditor)
            env["GIT_EDITOR"] = shlex.quote(messageEditor)

            targetArgs = ["--root"] if baseId is None else [str(baseId)]
            yield from _flowRebaseGit(
                self,
                "rebase", "--interactive", *argsIf(autostash, "--autostash"), *targetArgs,
                env=env,
                successStatus=_("Interactive rebase completed."))
        finally:
            shutil.rmtree(payloadDir, ignore_errors=True)

        if repo.state() == RepositoryState.NONE and not repo.any_conflicts:
            self.epilog.jumpTo = NavLocator.inCommit(repo.head_commit_id)
```

Notes for the implementer:
- `SortMode` and `RepositoryState` come from the existing `from gitfourchette.porcelain import *`; `messageSummary` from `from gitfourchette.toolbox import *`. Both star imports are already at the top of the file.
- `env` starts from `GIT_NO_EDITOR` and then *overrides* `GIT_EDITOR` with the helper — so if the helper's queue is exhausted the script still exits 0 (equivalent to `true`).
- The payload dir is cleaned up in `finally` even when the rebase pauses on a conflict: `git rebase --continue` never re-reads the todo, and the Phase 1 `ContinueRebase` runs with `GIT_EDITOR=true`, so pending reword/squash messages queued *after* a conflict pause degrade to git's defaults. That is the spec's accepted behavior ("unexpected editor invocations degrade gracefully").

- [ ] **Step 4: Register the task**

In `gitfourchette/tasks/__init__.py`, extend the rebasetasks block (lines 28–33), keeping it alphabetical:

```python
from gitfourchette.tasks.rebasetasks import (
    AbortRebase,
    ContinueRebase,
    InteractiveRebase,
    RebaseOnto,
    SkipRebase,
)
```

In `gitfourchette/tasks/taskbook.py`:
- `names` dict (sorted by label; the rebase entries sit at lines ~33/45/87/100): insert at the label-alphabetical position for "Interactive rebase":

```python
            tasks.InteractiveRebase: _("Interactive rebase"),
```

- `tips` dict (also label-sorted; `tasks.RebaseOnto` is at line ~145): insert at the label-alphabetical position:

```python
            tasks.InteractiveRebase: _("Reorder, drop, squash, or reword this commit and its descendants"),
```

- [ ] **Step 5: Add the graph context menu entry**

In `gitfourchette/graphview/graphview.py`:
- Extend the module's task import (the line importing `RebaseOnto`) with `InteractiveRebase`.
- In `_contextMenuActions1Commit`, directly after the `RebaseOnto` action (line ~474), insert:

```python
            TaskBook.action(self, InteractiveRebase, _("Interactive Reb&ase from Here…"), taskArgs=oid),
```

(`&a` is the only free mnemonic that fits the label; `&I` is taken by "Get &Info…". Verify no other `&a` exists in this menu.)

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py -x -q -k InteractiveRebase`
Expected: 5 PASS.

- [ ] **Step 7: Regression run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py test/test_rebasetodo.py test/test_rebasetododialog.py test/test_tasks_branch.py -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tasks/rebasetasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/graphview/graphview.py test/test_tasks_rebase.py
git commit -m "feat: InteractiveRebase task wired to commit graph

git rebase -i driven through GIT_SEQUENCE_EDITOR/GIT_EDITOR helper
scripts generated per invocation; reorder/drop/squash/fixup/reword.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Hardening — conflicts, abort, cancel, merge flattening, autostash

No new features expected; these tests exercise the seams between Phase 2 and the Phase 1 banner/ConflictView machinery, plus the dialog's warning and autostash paths end-to-end. Fix whatever they flush out.

**Files:**
- Test: `test/test_tasks_rebase.py` (append)
- Possibly fix: `gitfourchette/tasks/rebasetasks.py`, `gitfourchette/forms/rebasetododialog.py` (only if tests expose bugs)

**Interfaces:**
- Consumes: `makeLinearHistory`, `_commitIdByMessage`, `_logSummaries`, `_openTodoDialog`, `_bannerButton`, `REBASE_STATES_FOR_TESTS` from earlier tasks (all in `test/test_tasks_rebase.py`).
- Produces: `makeDependentHistory(tempDir) -> str` test helper.

- [ ] **Step 1: Write the tests**

Append to `test/test_tasks_rebase.py`:

```python
def makeDependentHistory(tempDir) -> str:
    """Branch 'work' where 'ir: beta' depends on 'ir: alpha' (same file),
    so dropping alpha makes beta conflict; 'ir: own' is independent."""
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c work master
        echo base > shared.txt
        git add shared.txt
        git commit -m "ir: base"
        echo alpha > shared.txt
        git add shared.txt
        git commit -m "ir: alpha"
        echo beta > shared.txt
        git add shared.txt
        git commit -m "ir: beta"
        echo own > own.txt
        git add own.txt
        git commit -m "ir: own"
        """,
        wd)
    return wd


def testInteractiveRebaseConflictResolveContinue(tempDir, mainWindow):
    wd = makeDependentHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: alpha")
    assert [r.summary for r in dlg.rows()] == ["ir: own", "ir: beta", "ir: alpha"]
    dlg.setAction(2, "drop")  # drop alpha -> beta conflicts at step 1 of 2
    dlg.accept()

    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.repo.any_conflicts
    assert rw.mergeBanner.isVisibleTo(rw)

    # Resolve by taking THEIRS (the replayed commit's version: "beta")
    rw.jump(NavLocator.inUnstaged("shared.txt"))
    assert rw.conflictView.isVisibleTo(rw)
    rw.conflictView.ui.theirsButton.click()

    _bannerButton(rw, r"continue").click()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: own", "ir: beta"]
    assert readFile(f"{wd}/shared.txt").decode().strip() == "beta"
    headTree = rw.repo.peel_commit(rw.repo.head_commit_id).tree
    assert "own.txt" in headTree


def testInteractiveRebaseAbortRestoresBranch(tempDir, mainWindow):
    wd = makeDependentHistory(tempDir)
    rw = mainWindow.openRepo(wd)
    oldTip = rw.repo.branches.local["work"].target

    dlg = _openTodoDialog(rw, "ir: alpha")
    dlg.setAction(2, "drop")
    dlg.accept()
    assert rw.repo.state() in REBASE_STATES_FOR_TESTS

    _bannerButton(rw, r"abort").click()
    acceptQMessageBox(rw, r"abort.+rebase")

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["work"].target == oldTip


def testInteractiveRebaseCancelDialog(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)
    oldTip = rw.repo.branches.local["work"].target

    dlg = _openTodoDialog(rw, "ir: one")
    dlg.reject()

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["work"].target == oldTip


def testInteractiveRebaseWarnsAboutFlattenedMerges(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c work master
        echo one > one.txt
        git add one.txt
        git commit -m "ir: one"
        git switch -c side
        echo side > side.txt
        git add side.txt
        git commit -m "side: extra"
        git switch work
        echo two > two.txt
        git add two.txt
        git commit -m "ir: two"
        git merge side -m "merge side into work"
        """,
        wd)
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    summaries = [r.summary for r in dlg.rows()]
    assert "merge side into work" not in summaries  # merge commit excluded
    assert set(summaries) == {"ir: two", "side: extra", "ir: one"}
    assert summaries[-1] == "ir: one"  # oldest at the bottom
    assert dlg.mergeWarningLabel.isVisibleTo(dlg)
    dlg.reject()  # don't execute; flattening semantics are git's own

    assert rw.repo.state() == RepositoryState.NONE


def testInteractiveRebaseDirtyAutostash(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    writeFile(f"{wd}/one.txt", "one dirty\n")  # tracked file, uncommitted change
    rw = mainWindow.openRepo(wd)

    dlg = _openTodoDialog(rw, "ir: one")
    assert dlg.autostashCheckBox.isVisibleTo(dlg)
    assert dlg.autostash()
    dlg.moveRow(0, 1)
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.repo.any_conflicts
    assert _logSummaries(rw.repo, 3) == ["ir: two", "ir: three", "ir: one"]
    # The dirty change survived the autostash round-trip; no stash left behind
    assert readFile(f"{wd}/one.txt").decode() == "one dirty\n"
    assert len(rw.repo.listall_stashes()) == 0
```

- [ ] **Step 2: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py -x -q -k InteractiveRebase`
Expected: all PASS. If a test fails, debug the product code (or an inaccurate scenario) — do NOT weaken an assertion to make it pass. Known trap: in `testInteractiveRebaseConflictResolveContinue`, the ConflictView button name must match Phase 1's `testRebaseConflictResolveAndContinue` (it drives `rw.conflictView.ui.theirsButton`).

- [ ] **Step 3: Full rebase + neighbors regression run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py test/test_rebasetodo.py test/test_rebasetododialog.py test/test_tasks_branch.py test/test_tasks_conflict.py -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add test/test_tasks_rebase.py
git commit -m "test: interactive rebase conflict, abort, cancel, merge and autostash coverage

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(Include any product-code fixes this task forced in the same commit, and mention them in the commit body.)

---

### Task 6: Full-suite verification

**Files:**
- None expected (fixes only if the suite exposes regressions).

**Interfaces:**
- Consumes: everything above.
- Produces: green full suite on `fork-main`.

- [ ] **Step 1: Full test suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 0 failed (Phase 1 baseline was 927 passed / 16 skipped; expect ~+25 passed). Any failure must be triaged: if it also fails on the pre-Phase-2 commit (`git stash` / check out the Task-1 parent), it's pre-existing; otherwise fix it now.

- [ ] **Step 2: Sanity-check the app imports & version**

Run: `.venv/bin/python -c "import gitfourchette.tasks as t; print(t.InteractiveRebase); import gitfourchette.appconsts as a; print(a.APP_VERSION)"`
Expected: prints the class and `1.9.1+fork`.

- [ ] **Step 3: Manual smoke test (deferred to user)**

Note for the session log: launch `.venv/bin/python -m gitfourchette`, open a scratch repo, right-click a commit → "Interactive Rebase from Here…", check the dialog renders, drag a row, set an action via the combo, cancel. The automated suite covers behavior; this checks look & feel only. Do not block on it.

- [ ] **Step 4: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix: full-suite fallout from interactive rebase

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
