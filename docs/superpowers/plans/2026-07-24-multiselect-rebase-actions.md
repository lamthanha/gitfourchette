# Multi-Select Rebase Actions (Phase 2 Addendum) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork-parity actions on a multi-commit graph selection: **S&quash n Commits…** (immediate execution with a message prompt, Fork-style — no todo dialog) and **&Drop n Commits…** (confirm, then execute), plus **Interactive Reb&ase from Here…** anchored at the oldest selected commit. Today a 3+ selection shows "No actions available for this selection".

**Architecture:** Extract the todo-preparation and todo-execution halves of `InteractiveRebase.flow` into shared generators (`_flowPrepareTodo`, `_flowExecuteTodo`) in `gitfourchette/tasks/rebasetasks.py`. New `SquashCommits`/`DropCommits` tasks build a preset todo programmatically (no `RebaseTodoDialog`) and run it through the same helper-script machinery. A small `SquashMessageDialog` (multiline message + optional autostash checkbox) lives in `gitfourchette/forms/rebasetododialog.py`. The graph learns an N-commit context menu.

**Tech Stack:** Python ≥3.10, PyQt6, pygit2 (reads only), pytest + pytest-qt, real `git` binary via GitDriver.

## Global Constraints

- Repo: `/home/admin/workspace.personal/gitfourchette`, branch `fork-main`. Spec: `docs/superpowers/specs/2026-07-24-gitfourchette-fork-design.md`; this addendum extends its Phase 2 with a user-approved feature (2026-07-24): Fork-style multi-select squash/drop with **immediate execution** (message prompt only — no todo dialog).
- Test runner prefix (always): `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`.
- Every user-facing string via `_("...")` / `_n(...)`; typographic `…` and `’`.
- All rebase execution through the existing helper-script machinery (`_writeRebaseScripts` + `_flowRebaseGit` with the script env) — never pygit2 mutation, never a new git-driving path.
- New tasks registered in `gitfourchette/tasks/__init__.py` (import block alphabetical) AND `TaskBook.names` + `tips` in `taskbook.py` (both dicts sorted by **label text**). No `icons` entries.
- Menu mnemonics: the N-commit menu coexists with the 2-commit menu (`&Swap A/B`, `E&xport A/B Diff As Patch…`), so: **S&quash** (`&q`), **&Drop** (`&D`), **Interactive Reb&ase from Here…** (`&a`). Never `&S` (Swap).
- Behavior invariants that MUST NOT change (existing tests pin them): `InteractiveRebase` dialog flow, stale-HEAD guard, payload-dir cleanup in `finally`, jump-to-HEAD on full success, worker-thread hops around pygit2 reads, dirty-tree → autostash-offer pattern.
- pygit2 `Branch.is_checked_out()` is worktree-wide — never use it to mean "is the current branch".
- TDD: failing test first. Commit per task with trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Key existing facts (verified against the tree at b96b4306)

- `GraphView.locatorFromSelection` (`graphview.py:212-258`): >2 selected rows → `NavLocator.inSpecial(SpecialRow.TooManyRowsSelected)`; `onContextMenuRequested` (`:370-397`) has no branch for it → falls to the disabled "No actions available" entry. Exactly 2 commits → `locator.commitDiffAB()` → `_contextMenuActions2Commits` (`:490-500`).
- `self.selectedIndexes()` is unsorted; each index carries `CommitLogModel.Role.SpecialRow` and `Role.Oid`; the workdir row's oid is `UC_FAKEID`.
- `TaskBook.action(...).replace(enabled=...)` is the established disabled-entry pattern (sidebar rebase entry).
- Multi-select in tests: `qlvClickNthRow(rw.graphView, row)` then `qlvClickNthRow(rw.graphView, row2, modifier=Qt.KeyboardModifier.ControlModifier)` (`test/test_graphview.py:665-666`).
- In `makeLinearHistory` repos the graph rows are deterministic: row 0 = Uncommitted Changes, row 1 = "ir: three", row 2 = "ir: two", row 3 = "ir: one", row 4 = master tip.
- `flowConfirm(text=..., verb=..., icon=..., checkbox=...)` attaches a QCheckBox to the QMessageBox (Phase 1 autostash pattern).
- `planEditorMessages`: within one squash chain, the **last non-empty squash-row message in execution order wins** — so the combined message goes on the **newest** selected row (last executed of the chain).

---

### Task 1: Behavior-neutral refactor — extract `_flowPrepareTodo` / `_flowExecuteTodo`

No new features, no new tests. The existing 27 rebase tests are the safety net; they must pass unchanged.

**Files:**
- Modify: `gitfourchette/tasks/rebasetasks.py` (restructure `InteractiveRebase.flow` into two shared generators + a thin flow)

**Interfaces:**
- Consumes: everything currently inside `InteractiveRebase.flow`.
- Produces (exact signatures Task 2 relies on):
  - `_flowPrepareTodo(task: RepoTask, fromCommit: Oid)` — generator (use with `yield from`); returns `(rowsNewestFirst: list[RebaseTodoRow], baseId: Oid | None, flattenedMerges: int, dirty: bool, headId: Oid)`. Contains: the `RepositoryState.NONE` guard, the ancestor guard, the worker-thread walk with merge exclusion, the dirty probe, and the "no commits to edit" abort.
  - `_flowExecuteTodo(task: RepoTask, execRows: list[RebaseTodoRow], baseId: Oid | None, headId: Oid, autostash: bool, successStatus: str)` — generator; contains: the stale-HEAD/state re-check, `validateTodo` guard (as `AbortTask(todoError)`), payload dir + `_writeRebaseScripts` + env overlay + `_flowRebaseGit(... env=env)` + `finally` cleanup, and the worker-hopped jump-to-HEAD epilog.

- [ ] **Step 1: Restructure**

In `gitfourchette/tasks/rebasetasks.py`, cut `InteractiveRebase.flow` into the two generators above (module-level functions, placed next to `_writeRebaseScripts`), so that `InteractiveRebase.flow` becomes exactly:

```python
    def flow(self, fromCommit: Oid):
        repo = self.repo

        rows, baseId, flattenedMerges, dirty, headId = yield from _flowPrepareTodo(self, fromCommit)

        dlg = RebaseTodoDialog(rows, flattenedMerges, dirty, self.parentWidget())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        execRows = dlg.executionRows()
        autostash = dlg.autostash()

        yield from _flowExecuteTodo(self, execRows, baseId, headId, autostash,
                                    successStatus=_("Interactive rebase completed."))
```

Move code verbatim — do not reword strings, reorder guards, or change thread-hop placement. The stale-HEAD guard and the `todoError` guard both live at the top of `_flowExecuteTodo` (they currently sit between the dialog and the payload work; moving them into the execute helper preserves order).

- [ ] **Step 2: Run the full rebase-family suites**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py test/test_rebasetodo.py test/test_rebasetododialog.py -q`
Expected: 49 passed, unchanged.

- [ ] **Step 3: Full suite once**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 967 passed / 16 skipped (same as pre-refactor).

- [ ] **Step 4: Commit**

```bash
git add gitfourchette/tasks/rebasetasks.py
git commit -m "refactor: extract shared todo prepare/execute helpers for rebase tasks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `SquashCommits`, `DropCommits`, `SquashMessageDialog`, N-commit menu

**Files:**
- Modify: `gitfourchette/forms/rebasetododialog.py` (append `SquashMessageDialog`)
- Modify: `gitfourchette/tasks/rebasetasks.py` (two new task classes)
- Modify: `gitfourchette/tasks/__init__.py`, `gitfourchette/tasks/taskbook.py` (registration)
- Modify: `gitfourchette/graphview/graphview.py` (`selectedCommitIds` helper; `_contextMenuActionsNCommits`; two dispatch hooks in `onContextMenuRequested`)
- Test: `test/test_tasks_rebase.py` (append)

**Interfaces:**
- Consumes: `_flowPrepareTodo` / `_flowExecuteTodo` (Task 1, exact signatures above); `combinedSquashMessage`, `validateTodo` from `gitfourchette.rebasetodo`; `qlvClickNthRow` from `test/util.py`.
- Produces:
  - `SquashMessageDialog(prefillMessage: str, commitCount: int, offerAutostash: bool, parent=None)` with `.message() -> str`, `.autostash() -> bool`, attributes `.messageEdit`, `.autostashCheckBox`, `.okButton`; OK disabled while the message is blank; window title contains "Squash" + count (findQDialog pattern `r"squash.+commits"`).
  - `class SquashCommits(RepoTask)` / `class DropCommits(RepoTask)`, both `flow(self, oids: tuple[Oid, ...])` where `oids` is the selection **newest-first**.
  - `GraphView.selectedCommitIds() -> tuple[list[Oid], bool]` (oids newest-first by row, contiguity flag).
  - `GraphView._contextMenuActionsNCommits() -> list | None` (None when fewer than 2 commit rows selected).

- [ ] **Step 1: Write the failing tests**

Append to `test/test_tasks_rebase.py`:

```python
def testSquashSelectedCommits(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    # Rows: 1="ir: three", 2="ir: two" (contiguous pair; anchor = oldest = "ir: two")
    qlvClickNthRow(rw.graphView, 1)
    qlvClickNthRow(rw.graphView, 2, modifier=Qt.KeyboardModifier.ControlModifier)
    triggerContextMenuAction(rw.graphView.viewport(), r"squash 2 commits")

    dlg = findQDialog(rw, r"squash.+commits")
    prefill = dlg.messageEdit.toPlainText()
    assert "ir: two" in prefill
    assert "ir: three" in prefill
    assert not dlg.autostashCheckBox.isVisibleTo(dlg)  # clean tree
    dlg.messageEdit.setPlainText("ir: 2+3\n\nSquashed by test.")
    assert dlg.okButton.isEnabled()
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 2) == ["ir: 2+3", "ir: one"]
    head = rw.repo.peel_commit(rw.repo.head_commit_id)
    assert "Squashed by test." in head.message
    assert "two.txt" in head.tree
    assert "three.txt" in head.tree


def testSquashBlankMessageDisablesOk(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)
    oldTip = rw.repo.branches.local["work"].target

    qlvClickNthRow(rw.graphView, 1)
    qlvClickNthRow(rw.graphView, 2, modifier=Qt.KeyboardModifier.ControlModifier)
    triggerContextMenuAction(rw.graphView.viewport(), r"squash 2 commits")

    dlg = findQDialog(rw, r"squash.+commits")
    dlg.messageEdit.setPlainText("   ")
    assert not dlg.okButton.isEnabled()
    dlg.reject()
    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["work"].target == oldTip


def testDropSelectedCommitsNonContiguous(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    # Rows 1="ir: three" and 3="ir: one" -- non-contiguous; drop both, keep "ir: two"
    qlvClickNthRow(rw.graphView, 1)
    qlvClickNthRow(rw.graphView, 3, modifier=Qt.KeyboardModifier.ControlModifier)
    triggerContextMenuAction(rw.graphView.viewport(), r"drop 2 commits")
    acceptQMessageBox(rw, r"drop.+2.+commits")

    assert rw.repo.state() == RepositoryState.NONE
    assert _logSummaries(rw.repo, 1) == ["ir: two"]
    headTree = rw.repo.peel_commit(rw.repo.head_commit_id).tree
    assert "two.txt" in headTree
    assert "one.txt" not in headTree
    assert "three.txt" not in headTree


def testSquashDisabledForNonContiguousSelection(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.graphView, 1)
    qlvClickNthRow(rw.graphView, 3, modifier=Qt.KeyboardModifier.ControlModifier)
    actions = rw.graphView._contextMenuActionsNCommits()
    squashAction = next(a for a in actions
                        if getattr(a, "caption", "") and "quash" in a.caption)
    dropAction = next(a for a in actions
                      if getattr(a, "caption", "") and "Drop" in a.caption)
    assert not squashAction.enabled
    assert dropAction.enabled


def testSquashSelectionWithMergeAborts(tempDir, mainWindow):
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
    oldTip = rw.repo.branches.local["work"].target

    # Row 1 is the merge commit (HEAD); row 2 is a non-merge commit either way
    qlvClickNthRow(rw.graphView, 1)
    qlvClickNthRow(rw.graphView, 2, modifier=Qt.KeyboardModifier.ControlModifier)
    triggerContextMenuAction(rw.graphView.viewport(), r"squash 2 commits")
    acceptQMessageBox(rw, r"merge")

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.branches.local["work"].target == oldTip


def testSquashDirtyAutostash(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    writeFile(f"{wd}/one.txt", "one dirty\n")
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.graphView, 1)
    qlvClickNthRow(rw.graphView, 2, modifier=Qt.KeyboardModifier.ControlModifier)
    triggerContextMenuAction(rw.graphView.viewport(), r"squash 2 commits")

    dlg = findQDialog(rw, r"squash.+commits")
    assert dlg.autostashCheckBox.isVisibleTo(dlg)
    assert dlg.autostash()
    dlg.messageEdit.setPlainText("ir: 2+3")
    dlg.accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.repo.any_conflicts
    assert _logSummaries(rw.repo, 2) == ["ir: 2+3", "ir: one"]
    assert readFile(f"{wd}/one.txt").decode() == "one dirty\n"
    assert len(rw.repo.listall_stashes()) == 0


def testInteractiveRebaseFromMultiSelection(tempDir, mainWindow):
    wd = makeLinearHistory(tempDir)
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.graphView, 1)
    qlvClickNthRow(rw.graphView, 2, modifier=Qt.KeyboardModifier.ShiftModifier)
    # Anchored at the OLDEST selected commit ("ir: two") -> todo covers two..HEAD
    triggerContextMenuAction(rw.graphView.viewport(), r"interactive rebase")
    dlg = findQDialog(rw, r"interactive rebase")
    assert [r.summary for r in dlg.rows()] == ["ir: three", "ir: two"]
    dlg.reject()
    assert rw.repo.state() == RepositoryState.NONE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py -x -q -k "Squash or Drop or FromMultiSelection"`
Expected: FAIL — `triggerContextMenuAction` finds no `squash 2 commits` item (menu shows the disabled "No actions available" fallback).

- [ ] **Step 3: Add `SquashMessageDialog`**

Append to `gitfourchette/forms/rebasetododialog.py`:

```python
class SquashMessageDialog(QDialog):
    """Fork-style immediate squash: just the combined message and an optional
    autostash checkbox — the todo itself is preset by SquashCommits."""

    def __init__(self, prefillMessage: str, commitCount: int, offerAutostash: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("SquashMessageDialog")
        self.setWindowTitle(_("Squash {0} Commits", commitCount))
        self.setModal(True)
        self._offerAutostash = offerAutostash

        promptLabel = QLabel(_("Commit message for the squashed commit:"), self)

        self.messageEdit = QPlainTextEdit(self)
        self.messageEdit.setPlainText(prefillMessage)
        self.messageEdit.textChanged.connect(self._revalidate)

        self.autostashCheckBox = QCheckBox(
            _("Autostash (stash uncommitted changes, then reapply them)"), self)
        self.autostashCheckBox.setChecked(True)
        self.autostashCheckBox.setVisible(offerAutostash)

        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.okButton = self.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.okButton.setText(_("&Squash"))

        layout = QVBoxLayout(self)
        layout.addWidget(promptLabel)
        layout.addWidget(self.messageEdit)
        layout.addWidget(self.autostashCheckBox)
        layout.addWidget(self.buttonBox)
        self.resize(540, 320)
        self._revalidate()

    def _revalidate(self):
        self.okButton.setEnabled(bool(self.messageEdit.toPlainText().strip()))

    def message(self) -> str:
        return self.messageEdit.toPlainText()

    def autostash(self) -> bool:
        return self._offerAutostash and self.autostashCheckBox.isChecked()
```

- [ ] **Step 4: Add the two tasks**

In `gitfourchette/tasks/rebasetasks.py` (extend the `rebasetododialog` import with `SquashMessageDialog`; place the classes after `InteractiveRebase`):

```python
def _mapSelectionToRows(rows: list[RebaseTodoRow], oids: tuple[Oid, ...]) -> list[int]:
    """Indices (into newest-first rows) of the selected commits. Aborts if any
    selected commit is absent from the todo (merge commit, or outside the
    range walked from the oldest selection to HEAD)."""
    rowIndexByOid = {row.oid: i for i, row in enumerate(rows)}
    try:
        return sorted(rowIndexByOid[str(oid)] for oid in oids)
    except KeyError:
        raise AbortTask(_("Can’t rewrite this selection: it includes a merge commit "
                          "or a commit outside the current branch’s history."))


class SquashCommits(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, oids: tuple[Oid, ...]):
        assert len(oids) >= 2
        rows, baseId, _flattenedMerges, dirty, headId = yield from _flowPrepareTodo(self, oids[-1])

        indices = _mapSelectionToRows(rows, oids)
        if indices != list(range(indices[0], indices[-1] + 1)):
            raise AbortTask(_("Can’t squash a non-contiguous selection of commits."))

        # rows is newest-first: the LAST selected index is the oldest commit —
        # it stays "pick" and becomes the squash target; the rest fold into it.
        for i in indices[:-1]:
            rows[i].action = "squash"
        execRows = list(reversed(rows))

        prefill = combinedSquashMessage(execRows, execRows.index(rows[indices[0]]))
        dlg = SquashMessageDialog(prefill, len(indices), dirty, self.parentWidget())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        # rows[indices[0]] is the chain's last-executed squash row: its message wins
        rows[indices[0]].message = dlg.message()
        autostash = dlg.autostash()

        yield from _flowExecuteTodo(
            self, execRows, baseId, headId, autostash,
            successStatus=_("Squashed {0} commits into one.", len(indices)))


class DropCommits(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, oids: tuple[Oid, ...]):
        rows, baseId, _flattenedMerges, dirty, headId = yield from _flowPrepareTodo(self, oids[-1])

        for i in _mapSelectionToRows(rows, oids):
            rows[i].action = "drop"
        execRows = list(reversed(rows))

        todoError = validateTodo(execRows)
        if todoError:
            raise AbortTask(todoError)

        autostashCheckbox = None
        if dirty:
            autostashCheckbox = QCheckBox(_("Autostash (stash uncommitted changes, then reapply them)"))
            autostashCheckbox.setChecked(True)
        text = paragraphs(
            _n("Do you want to drop {n} commit?", "Do you want to drop {n} commits?", n=len(oids)),
            _("This rewrites the branch’s history."))
        if autostashCheckbox is not None:
            yield from self.flowConfirm(text=text, verb=_("Drop"), icon="warning",
                                        checkbox=autostashCheckbox)
        else:
            yield from self.flowConfirm(text=text, verb=_("Drop"), icon="warning")
        autostash = autostashCheckbox is not None and autostashCheckbox.isChecked()

        yield from _flowExecuteTodo(
            self, execRows, baseId, headId, autostash,
            successStatus=_n("Dropped {n} commit.", "Dropped {n} commits.", n=len(oids)))
```

Note: `combinedSquashMessage` and `validateTodo` must be added to the existing `gitfourchette.rebasetodo` import block in this file.

- [ ] **Step 5: Register the tasks**

`gitfourchette/tasks/__init__.py` — rebasetasks block, alphabetical:

```python
from gitfourchette.tasks.rebasetasks import (
    AbortRebase,
    ContinueRebase,
    DropCommits,
    InteractiveRebase,
    RebaseOnto,
    SkipRebase,
    SquashCommits,
)
```

`taskbook.py` `names` (label-alphabetical): `tasks.DropCommits: _("Drop commits"),` and `tasks.SquashCommits: _("Squash commits"),`
`taskbook.py` `tips` (label-alphabetical): `tasks.DropCommits: _("Remove the selected commits from the branch’s history"),` and `tasks.SquashCommits: _("Combine the selected commits into one"),`

- [ ] **Step 6: Graph menu**

In `gitfourchette/graphview/graphview.py`:

1. Add to `GraphView` (near `locatorFromSelection`):

```python
    def selectedCommitIds(self) -> tuple[list[Oid], bool]:
        """Oids of the selected commit rows (newest first, i.e. by ascending
        graph row), and whether those rows are contiguous."""
        byRow = {}
        for index in self.selectedIndexes():
            if index.data(CommitLogModel.Role.SpecialRow) != SpecialRow.Commit:
                continue
            oid = index.data(CommitLogModel.Role.Oid)
            if oid and oid != UC_FAKEID:
                byRow[index.row()] = oid
        rowNumbers = sorted(byRow)
        contiguous = bool(rowNumbers) and rowNumbers[-1] - rowNumbers[0] == len(rowNumbers) - 1
        return [byRow[r] for r in rowNumbers], contiguous
```

2. Add the menu builder (after `_contextMenuActions2Commits`):

```python
    def _contextMenuActionsNCommits(self):
        oids, contiguous = self.selectedCommitIds()
        n = len(oids)
        if n < 2:
            return None
        taskArgs = (tuple(oids),)
        return [
            TaskBook.action(self, SquashCommits, _("S&quash {0} Commits…", n),
                            taskArgs=taskArgs).replace(enabled=contiguous),
            TaskBook.action(self, DropCommits, _("&Drop {0} Commits…", n),
                            taskArgs=taskArgs),
            ActionDef.SEPARATOR,
            TaskBook.action(self, InteractiveRebase, _("Interactive Reb&ase from Here…"),
                            taskArgs=oids[-1]),
        ]
```

3. In `onContextMenuRequested`: in the `NavContext.SPECIAL` branch (line ~383), add after the TruncatedHistory case:

```python
            elif special == SpecialRow.TooManyRowsSelected:
                actions = self._contextMenuActionsNCommits()
```

and in the COMMITTED/`commitDiffAB` branch (line ~378), replace `actions = self._contextMenuActions2Commits(locator)` with:

```python
                actions = self._contextMenuActions2Commits(locator)
                nCommitActions = self._contextMenuActionsNCommits()
                if nCommitActions:
                    actions += [ActionDef.SEPARATOR, *nCommitActions]
```

4. `SquashCommits` / `DropCommits` reach this module through the existing `from gitfourchette.tasks import *` (no new import line — same as `InteractiveRebase`). `UC_FAKEID` is already imported by this module (used in `locatorFromSelection`); verify, and add to the porcelain import only if absent.

- [ ] **Step 7: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py -x -q -k "Squash or Drop or FromMultiSelection"`
Expected: 7 PASS. If `testSquashDisabledForNonContiguousSelection` fails on the `caption`/`enabled` attribute names, check the `ActionDef` dataclass in `gitfourchette/toolbox/` for the real field names and adjust the test's attribute access (only that).

- [ ] **Step 8: Regression run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_rebase.py test/test_rebasetodo.py test/test_rebasetododialog.py test/test_graphview.py -q`
Expected: all PASS (the 2-commit diff menu tests in test_graphview must still pass with the appended actions).

- [ ] **Step 9: Commit**

```bash
git add gitfourchette/forms/rebasetododialog.py gitfourchette/tasks/rebasetasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/graphview/graphview.py test/test_tasks_rebase.py
git commit -m "feat: Fork-style squash/drop on multi-commit graph selection

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Full-suite verification

**Files:** none expected.

- [ ] **Step 1: Full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 0 failed (~974 passed / 16 skipped). Triage any failure: pre-existing on b96b4306 vs introduced; fix regressions.

- [ ] **Step 2: Manual smoke (deferred to user)**

Note for the session log: select several commits in a real repo → right-click → check Squash/Drop entries, squash greyed out for a non-contiguous selection, and the squash message dialog feel. Do not block on it.

- [ ] **Step 3: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix: full-suite fallout from multi-select rebase actions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
