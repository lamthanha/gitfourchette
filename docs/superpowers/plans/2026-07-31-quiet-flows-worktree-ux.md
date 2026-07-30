# Quiet Flows & Worktree UX Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ten small Fork-parity UX features: quiet branch switch, quiet worktree open, New Worktree dialog fixes (width, radio auto-select, path template, remote-branch prefill), MoveWorktree, same-repo tab adjacency, plain tab titles, and an honest "Commit and Push" dialog caption.

**Architecture:** Almost everything extends existing fork modules (`tasks/worktreetasks.py`, `forms/newworktreedialog.py`, `worktrees.py`). Upstream-file edits are deliberately minimal: one conditional in `branchtasks.py` (quiet switch), one optional parameter in `committasks.py` (caption), one hook + one deletion in `mainwindow.py` (tabs). Mutations run the real git binary via `RepoTask.flowCallGit`; pygit2 stays read-only.

**Tech Stack:** PyQt6, pygit2 (reads only), real git binary via GitDriver, pytest offscreen.

**Spec:** `docs/superpowers/specs/2026-07-31-quiet-flows-worktree-ux-design.md`

## Global Constraints

- Test runner prefix: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` from the worktree root. Full suite must be **0 failed** on top of baseline (**1082 passed / 16 skipped** at branch point `fdcc0faa`). Per-task expected counts below are the arithmetic expectation; 0 failed is the hard requirement.
- Mutations (`checkout`, `worktree add/move`, `push`) run the real git binary via `RepoTask.flowCallGit(...)` — NEVER reimplement in pygit2.
- **Task 6 edits `tasks/__init__.py` and `taskbook.py`** (new task `MoveWorktree`): register in BOTH — the worktreetasks import block (names alphabetized within the block) and `TaskBook.names` at the alphabetical slot. NO `TaskBook.icons` entries (fork rule).
- UI strings `_("...")` localized, typographic `…` and `’`; every new `&X` mnemonic unique within its menu (worked out per task below — re-verify at implementation time).
- `Branch.is_checked_out()` is worktree-wide — never use it to mean "current branch". Not needed in this plan; do not introduce it.
- TDD; one commit per task with trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Ruff: `.venv/bin/python -m ruff check` must stay green (repo is green under the pinned config).
- Do NOT touch the held-in-another-worktree open-offer path in `SwitchBranch` (`branchtasks.py:39-60`), the detached-HEAD warning (`branchtasks.py:76-87`), or `test_worktrees.py`'s open-offer tests (~lines 499/510) — those behaviors are spec-mandated keepers.

## Verified codebase facts (from exploration — do not re-derive)

- `SwitchBranch.flow` (`branchtasks.py:25-98`): held-elsewhere offer at 39-60; confirmation block at 61-72 (exact text below in Task 1); detached-HEAD warning at ~76-87 fires **independently** of `askForConfirmation`; checkout via `flowCallGit("checkout", "--progress", "--no-guess", *argsIf(recurseSubmodules, "--recurse-submodules"), newBranch)`.
- Tests pinning the switch confirm (each does `acceptQMessageBox(rw, "switch…")` right after triggering a switch): `test_sidebar.py:451`; `test_tasks_branch.py:676`, `:681` (two branches of one parametrized test), `:804` (dirty-clobber test — its SECOND box "local changes…overwritten by checkout" at ~:806 must stay), `:1211` (`testMightLoseDetachedHead` — its "lose track of this commit" box at ~:1212 must stay), `:1263`. **NOT a switch confirm:** `test_tasks_net.py:648` ("switch to.+local branch" is PushBranch's no-branch info box — leave it).
- `reposcenario.submodule(wd)` creates a submodule in a canned repo (usage: `test_tasks_submodule.py:26-28`); `test_tasks_branch.py` already imports `from . import reposcenario` (line 18).
- `findQMessageBox(parent, textPattern)` (`test/util.py:647`) returns the box; `qmb.checkBox()` pattern precedent in `test_tasks_rebase.py`. `findMenuAction` (`test/util.py:417`) **raises KeyError** when no menu item matches — assert absence with `pytest.raises(KeyError)`.
- `NewWorktree.flow(branchName="")` (`worktreetasks.py:21-52`): dialog → `worktree add` → `epilog.effects |= TaskEffects.Refs` → open-offer via `flowConfirmOpenNewWorktree` (42-52, to be deleted). `self.rw.openRepo.emit(path, NavLocator())` opens the tab.
- `RemoveWorktree.flow` (`worktreetasks.py:55-87`): main-worktree guard + `GFApplication.instance().mainWindow.tabWidgetForWorkdirPath(path)` tab guard — MoveWorktree copies both verbatim.
- `NewWorktreeDialog` (`forms/newworktreedialog.py`): fields `pathEdit`, `existingRadio`/`existingCombo`, `newRadio`/`newNameEdit`/`baseRefCombo`; prefill block at 41-43; default-path init at 45-50 (`self._mainRoot` from `repo.commondir`); signal wiring at 81-88; `_userEditedPath` defined at 87 (AFTER the prefill block, so prefill-time `setText` calls fire no connected slots); `_trackDefaultPath` at 97-100; `_revalidate` at 102-120; test API `setPath/setExistingBranch/setNewBranch/path/wantNewBranch/existingBranch/newBranchName/baseRef` at 129-157. Imports `porcelain`/`toolbox`/`qt` via star.
- Canned `TestGitRepository`: local branches `master` (checked out), `no-parent`; remote branches include `origin/master`, `origin/no-parent`, `origin/first-merge` (**no local `first-merge`**) — verify with `git branch -a` in an unpacked repo before finalizing tests; adjust names if they differ, do not weaken assertions.
- `TextInputDialog` (`forms/textinputdialog.py:12`): `__init__(parent, title, label, subtitle="", ...)`; public `self.lineEdit`; OK/Cancel buttonBox; `setMinimumWidth(512)`; works with `findQDialog` + `dlg.accept()`.
- `CommitDialog.acceptButton` is a **@property** (`forms/commitdialog.py:18-20`); plain-commit button caption is `_("Co&mmit")`, window title `_p("verb", "Commit")` (`commitdialog.py:52-60`). `NewCommit.flow()` (`committasks.py:35`) builds the dialog at 67-77; `flowSubtask(subtaskClass, *args, **kwargs)` forwards kwargs (`repotask.py:391`).
- `CommitAndPush` (`tasks/commitpushtasks.py`) runs `yield from self.flowSubtask(NewCommit)`; its tests (`test/test_shiftbuttons.py:17-64`) show the canned-remote idiom: `makeBareCopy(wd, addAsRemote="localfs", preFetch=True)`, `_stageFirstDirtyFile(rw)`, `findQDialog(rw, "commit")`, `dialog.acceptButton.click()`.
- `MainWindow._openRepo` (`mainwindow.py:642`): `tabIndex=-1` default → `self.tabs.insertTab(tabIndex, stub, title)` appends; `mainWindow.openRepo(path)` routes through it with default placement (line 599). `self.tabs.widgets()` iterates tab widgets; both `RepoWidget` and `RepoStub` have `.workdir`. `mainwindow.py` already imports `tabcolors`.
- `tabcolors.repoBindingKey(workdir)` (`tabcolors.py:69`): realpath of the **main worktree's root**, parses `.git` gitfiles/commondir directly (no pygit2, works for unloaded tabs).
- `MainWindow.refreshAllTabTexts` (`mainwindow.py:935-961`): computes `baseTitles`, then a duplicate-title disambiguation pass calling `disambiguateTabTitlesByPath(workdirs)` (only for non-nicknamed titles), then `setTabText(i, escamp(title))` + `refreshTabColors()`. `disambiguateTabTitlesByPath` lives at `toolbox/pathutils.py:30-51`, exported at `toolbox/__init__.py:37`; **only caller is mainwindow.py:954; no test references it**.
- Tab-text assertion idiom: `mainWindow.tabs.tabs.tabText(i)` (`test_worktrees.py:519-547`, the `[M]` tests). If offscreen elision ever interferes with an equality assert, `mainWindow.tabs.tabs.shadowText[i]` is the unelided bookkeeping list (`qtabwidget2.py:135-143`).
- Settings: `Prefs` dataclass (`settings.py:103`); `_category_git` block at 143-147 (ends `lfsAware`); plain `str` prefs auto-render as `QLineEdit` (`prefsdialog.py:520`). TrTables pref captions dict near `trtables.py:540`; the `"externalDiff_help"` entry shows the `_help` suffix + `_tokenReferenceTable({...})` pattern for documenting `$`-placeholders.
- `worktrees.py`: has `WorktreeInfo`, `parseWorktreeListPorcelain`, `listWorktrees`, `worktreeName` (line 63; uses `os`, so `os` is already imported).
- Sidebar: LocalBranch menu case at `sidebar.py:198-`; its NewWorktree entry currently `taskArgs=branchName` (~line 315); `refName` is in scope. RemoteBranch case at `sidebar.py:340-`; `worktreeActions` at ~352-353 (`openInWorktreeActionDef(localBranchWorktree)` or `[]`); `refName` in scope; taken mnemonics in the remote menu: B, F, M, C, r, H, A (`RenameRemoteBranch`/`DeleteRemoteBranch` auto-names carry no `&`) → **W is free**. Worktree leaf menu case: entries `&Open Worktree in New Tab` (O), `Open Worktree &Folder` (F), `Copy &Path` (P), separator, `RemoveWorktree` accel="R" → **M is free**. `findWorktreeCheckedOutOn` (`sidebar.py:1105`), `openInWorktreeActionDef` (`sidebar.py:1117`).
- `test_worktrees.py` (555 lines): `_openRepoWithLinkedWorktree(tempDir, mainWindow)` returns `(wd, linked, rw)`; `_worktreeNodeByPath(rw, path)` helper; NewWorktree tests at 186-260 (verbatim text in Task 2); open-offer tests at ~499/510 (leave alone). `unpackRepo(tempDir, testRepoName="TestGitRepository", renameTo="")` accepts a `str` dir too (`util.py:252-257`). Tests using `runShellScript` need the `mainWindow` fixture.
- The stash single-file restore pin (Task 9) was empirically validated this session: select stash → right-click file → "Restore File Revision… → As Of This Commit" restores only that file (menu items and flow confirmed on the CommittedFiles context menu; the confirm box matches `r"restore|workdir|working"`).

---

### Task 1: Quiet branch switch (A1)

**Files:**
- Modify: `gitfourchette/tasks/branchtasks.py:61-72`
- Modify: `test/test_sidebar.py:451`, `test/test_tasks_branch.py` (5 sites + 2 new tests)

**Interfaces:**
- Consumes: existing `SwitchBranch.flow` signature (unchanged).
- Produces: behavior only — no API change. Later tasks don't depend on this one.

- [ ] **Step 1: Write the failing tests** — append to `test/test_tasks_branch.py`:

```python
def testSwitchBranchQuietWhenNoSubmodules(tempDir, mainWindow):
    # Fork: submodule-free switch is silent (Fork-style quiet flow).
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert rw.repo.head_branch_shorthand == "master"

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), "switch to")

    # No confirmation box was shown: the switch has already completed.
    assert rw.repo.head_branch_shorthand == "no-parent"


def testSwitchBranchDialogKeptWithSubmodules(tempDir, mainWindow):
    # Fork: repos with submodules keep the confirm (recurse checkbox does real work).
    wd = unpackRepo(tempDir)
    reposcenario.submodule(wd)
    with RepoContext(wd) as repo:
        repo.create_branch_on_head("other")
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/other")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), "switch to")
    qmb = findQMessageBox(rw, "switch to")
    assert qmb.checkBox() is not None  # recurse-submodules checkbox present
    qmb.accept()
    assert rw.repo.head_branch_shorthand == "other"
```

(`reposcenario` is already imported at `test_tasks_branch.py:18`. If `reposcenario.submodule` leaves staged changes that block the checkout, switch to a branch created ON HEAD as shown — same tree, nothing to clobber.)

- [ ] **Step 2: Run tests to verify the first fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_branch.py -k "testSwitchBranchQuiet or testSwitchBranchDialogKept" -v`
Expected: `testSwitchBranchQuietWhenNoSubmodules` FAILS (head still `master`: the un-accepted confirm box blocks the flow). `testSwitchBranchDialogKeptWithSubmodules` may already pass — that's fine, it pins the keeper.

- [ ] **Step 3: Implement.** In `gitfourchette/tasks/branchtasks.py`, replace the block at lines 61-72:

```python
        if askForConfirmation:
            text = _("Do you want to switch to branch {0}?", bquo(newBranch))
            verb = _("Switch")

            recurseCheckbox = None
            anySubmodules = bool(self.repo.listall_submodules_fast())
            if anySubmodules:
                recurseCheckbox = QCheckBox(_("Update submodules recursively"))
                recurseCheckbox.setChecked(True)

            yield from self.flowConfirm(text=text, verb=verb, checkbox=recurseCheckbox)
            recurseSubmodules = recurseCheckbox is not None and recurseCheckbox.isChecked()
```

with:

```python
        if askForConfirmation:
            # Fork: Fork-style quiet switch — no confirmation dialog unless the
            # repo has submodules (the recurse checkbox does real work there).
            # Unsafe switches are still refused by git itself (clobber check),
            # and the detached-HEAD warning below fires regardless.
            recurseCheckbox = None
            anySubmodules = bool(self.repo.listall_submodules_fast())
            if anySubmodules:
                text = _("Do you want to switch to branch {0}?", bquo(newBranch))
                verb = _("Switch")
                recurseCheckbox = QCheckBox(_("Update submodules recursively"))
                recurseCheckbox.setChecked(True)
                yield from self.flowConfirm(text=text, verb=verb, checkbox=recurseCheckbox)
            recurseSubmodules = recurseCheckbox is not None and recurseCheckbox.isChecked()
```

- [ ] **Step 4: Adapt the pinning tests.** Delete exactly these `acceptQMessageBox` lines (the switch confirm no longer appears); keep every surrounding assertion verbatim:

1. `test_sidebar.py:451` — `acceptQMessageBox(rw, "switch")`
2. `test_tasks_branch.py:676` — `acceptQMessageBox(rw, "switch to")` (sidebarmenu branch)
3. `test_tasks_branch.py:681` — `acceptQMessageBox(rw, "switch to")` (sidebarkey branch)
4. `test_tasks_branch.py:804` — `acceptQMessageBox(rw, "switch to.+no-parent")` — KEEP the next line's "your local changes…overwritten by checkout" box (that's git's refusal, now the FIRST box)
5. `test_tasks_branch.py:1211` — `acceptQMessageBox(rw, "switch to")` — KEEP the "lose track of this commit" box
6. `test_tasks_branch.py:1263` — `acceptQMessageBox(rw, "do you want to switch to.+no-parent")`

Do NOT touch `test_tasks_net.py:648` (PushBranch info box, different dialog) or `test_worktrees.py` ~499/510 (held-elsewhere offer). If the full suite reveals another failing site whose error is an unconsumed "switch to" box, apply the same mechanical deletion — never delete clobber/detached/held-elsewhere boxes.

- [ ] **Step 5: Run the affected files**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_branch.py test/test_sidebar.py test/test_worktrees.py -q`
Expected: all pass.

- [ ] **Step 6: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1084 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 7: Commit**

```bash
git add gitfourchette/tasks/branchtasks.py test/test_tasks_branch.py test/test_sidebar.py
git commit -m "feat: quiet branch switch (dialog only when submodules present)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Quiet open of a newly created worktree (A2)

**Files:**
- Modify: `gitfourchette/tasks/worktreetasks.py` (NewWorktree tail; delete `flowConfirmOpenNewWorktree`)
- Modify: `test/test_worktrees.py:186-246` (3 tests)

**Interfaces:**
- Consumes: Task 1 not required (independent).
- Produces: `NewWorktree` opens the tab directly after success — Tasks 3/5's accept-path tests rely on "accept dialog → tab opens, zero message boxes".

- [ ] **Step 1: Adapt the tests to the new behavior (they become the failing tests).** Replace the three tests at `test/test_worktrees.py:186-246` with:

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

    # Fork: no "open it?" offer — the new worktree's tab opens directly.
    assert os.path.isdir(target)
    assert mainWindow.tabs.count() == 2
    assert os.path.realpath(mainWindow.currentRepoWidget().workdir) == os.path.realpath(target)
    # Original tab's sidebar refreshed with the new row
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2
    # The branch is checked out there
    from gitfourchette import worktrees
    infos = worktrees.listWorktrees(wd)
    assert infos[1].branch == "refs/heads/no-parent"


def testNewWorktreeNewBranchOpensTabQuietly(tempDir, mainWindow):
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

    assert mainWindow.tabs.count() == 2
    from gitfourchette import worktrees
    assert any(wt.branch == "refs/heads/no-parent" for wt in worktrees.listWorktrees(wd))
```

(`testNewWorktreeGitFailureSurfaced` at ~248 is untouched — its failure happens before the open step.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -k "NewWorktree or CheckoutBranchInNew" -v`
Expected: the three adapted tests FAIL (the un-consumed "open it?" box blocks the flow, so tab count stays 1).

- [ ] **Step 3: Implement.** In `gitfourchette/tasks/worktreetasks.py`, replace the tail of `NewWorktree.flow` and delete the helper:

```python
        self.epilog.effects |= TaskEffects.Refs

        # Fork-style quiet flow: open the new worktree's tab directly,
        # no "open it?" confirmation.
        self.rw.openRepo.emit(path, NavLocator())
```

(Delete the `openOffer = yield from ...` / `if openOffer:` lines and the entire `flowConfirmOpenNewWorktree` method. `NavLocator` import stays — it's still used here.)

- [ ] **Step 4: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -q`
Expected: all pass.

- [ ] **Step 5: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1084 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/tasks/worktreetasks.py test/test_worktrees.py
git commit -m "feat: open newly created worktree quietly (no confirmation dialog)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: New Worktree dialog — width + radio auto-select (B6, B7)

**Files:**
- Modify: `gitfourchette/forms/newworktreedialog.py`
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: Task 2 (accept → tab opens quietly; the typed-radio test relies on it).
- Produces: no API change; Task 5 builds on the same file.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def testNewWorktreeDialogWideEnoughForPath(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    assert dlg.width() >= 640
    dlg.reject()


def testNewWorktreeTypedNameSelectsNewBranchRadio(tempDir, mainWindow):
    # Open-list bug: typing a name while "existing branch" is checked used to
    # silently DISCARD the typed name and check out the combo's branch instead.
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "TypedWT")

    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    assert not dlg.wantNewBranch()
    QTest.keyClicks(dlg.newNameEdit, "typedbranch")
    assert dlg.wantNewBranch()  # radio flipped by typing
    assert dlg.newBranchName() == "typedbranch"
    dlg.setPath(target)
    dlg.accept()

    assert "typedbranch" in rw.repo.branches.local
    from gitfourchette import worktrees
    assert any(wt.branch == "refs/heads/typedbranch" for wt in worktrees.listWorktrees(wd))


def testNewWorktreeComboPickSelectsExistingRadio(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    dlg.setNewBranch("temp", "master")
    assert dlg.wantNewBranch()
    # Simulate a user pick on the existing-branch combo (activated = user gesture)
    dlg.existingCombo.activated.emit(dlg.existingCombo.currentIndex())
    assert not dlg.wantNewBranch()  # radio flipped back
    dlg.reject()
```

(`QTest` should be in scope via the test module's existing imports — check the import block of `test_worktrees.py` and mirror `test_tasks_branch.py` (`from gitfourchette.qt import ...` or util star) if it isn't.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -k "DialogWide or TypedName or ComboPick" -v`
Expected: 3 FAIL (width < 640; `wantNewBranch()` still False after typing; radio not flipped back).

- [ ] **Step 3: Implement.** In `gitfourchette/forms/newworktreedialog.py`:

(a) At the end of `__init__`, after `self._revalidate()` / `self.setModal(True)`:

```python
        # Open-list fix: widen so the path (the longest field) is readable.
        # max() so long translated labels can still widen it further.
        self.resize(max(640, self.width()), self.height())
```

(b) In the signal-wiring section of `__init__` (next to the existing `textEdited` connection at ~line 88), add:

```python
        # Open-list fix: typing a new-branch name means "create a new branch";
        # picking an existing branch from the combo means the opposite.
        # textEdited/activated fire on user gestures only, so the
        # setNewBranch()/setExistingBranch() test API stays inert here.
        self.newNameEdit.textEdited.connect(self._typedNewBranchName)
        self.existingCombo.activated.connect(self._pickedExistingBranch)
```

(c) Add the two methods next to `_trackDefaultPath`:

```python
    def _typedNewBranchName(self):
        if not self.newRadio.isChecked():
            self.newRadio.setChecked(True)  # toggled -> _revalidate
            self._trackDefaultPath()

    def _pickedExistingBranch(self, _index: int):
        if not self.existingRadio.isChecked():
            self.existingRadio.setChecked(True)
            self._trackDefaultPath()
```

- [ ] **Step 4: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -q`
Expected: all pass.

- [ ] **Step 5: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1087 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/forms/newworktreedialog.py test/test_worktrees.py
git commit -m "fix: New Worktree dialog width + radio follows typed branch name

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Worktree path template preference (B4)

**Files:**
- Modify: `gitfourchette/worktrees.py` (template constant + render function)
- Modify: `gitfourchette/settings.py` (`_category_git` block, after `lfsAware`)
- Modify: `gitfourchette/trtables.py` (caption + `_help` entry)
- Modify: `gitfourchette/forms/newworktreedialog.py` (`defaultPathForBranch`)
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: Task 3 (same dialog file, sequential edits).
- Produces: `worktrees.DEFAULT_WORKTREE_PATH_TEMPLATE: str`; `worktrees.renderWorktreePathTemplate(template: str, mainRoot: str, branch: str) -> str`; `Prefs.worktreePathTemplate: str`.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def testRenderWorktreePathTemplate():
    from gitfourchette.worktrees import renderWorktreePathTemplate
    assert renderWorktreePathTemplate(
        "$BASE_ROOT/$REPO_NAME-$BRANCH", "/home/u/ws/repo", "feature/x") \
        == os.path.normpath("/home/u/ws/repo-feature-x")
    assert renderWorktreePathTemplate(
        "$BASE_PATH-worktrees/$BRANCH", "/home/u/ws/repo", "main") \
        == os.path.normpath("/home/u/ws/repo-worktrees/main")
    # Unknown variables stay literal; blank template yields ""
    assert "$BOGUS" in renderWorktreePathTemplate("$BASE_ROOT/$BOGUS", "/r/x", "b")
    assert renderWorktreePathTemplate("   ", "/r/x", "b") == ""


def testNewWorktreeDialogHonorsPathTemplate(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    settings.prefs.worktreePathTemplate = "$BASE_PATH-worktrees/$BRANCH"

    from gitfourchette.tasks import NewWorktree
    NewWorktree.invoke(rw)
    dlg = findQDialog(rw, r"new worktree")
    branch = dlg.existingBranch()
    expected = os.path.normpath(f"{os.path.normpath(wd)}-worktrees/{branch}")
    assert os.path.normpath(dlg.path()) == expected
    dlg.reject()
```

(Test-mode settings are rebuilt per test by the harness — mutating `settings.prefs` directly is the established pattern; verify by checking any existing test that sets a pref, and follow it.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -k "Template" -v`
Expected: ImportError (`renderWorktreePathTemplate` doesn't exist) / AttributeError (`worktreePathTemplate`).

- [ ] **Step 3: Implement the render function.** Append to `gitfourchette/worktrees.py`:

```python
DEFAULT_WORKTREE_PATH_TEMPLATE = "$BASE_ROOT/$REPO_NAME-$BRANCH"


def renderWorktreePathTemplate(template: str, mainRoot: str, branch: str) -> str:
    """Expand $BASE_PATH / $BASE_ROOT / $REPO_NAME / $BRANCH in a worktree
    path template (vocabulary borrowed from VS Code's Git-worktree-manager).
    Unknown $VARS are left literal. Returns "" for a blank template."""
    if not template.strip():
        return ""
    mainRoot = os.path.normpath(mainRoot)
    leaf = branch.replace("/", "-") if branch else "worktree"
    for var, value in (
            ("$BASE_PATH", mainRoot),
            ("$BASE_ROOT", os.path.dirname(mainRoot)),
            ("$REPO_NAME", os.path.basename(mainRoot)),
            ("$BRANCH", leaf),
    ):
        template = template.replace(var, value)
    return os.path.normpath(template)
```

- [ ] **Step 4: Add the pref.** In `gitfourchette/settings.py`, `_category_git` block, after `lfsAware` (line ~147):

```python
    worktreePathTemplate        : str                   = "$BASE_ROOT/$REPO_NAME-$BRANCH"
```

(Align the column padding with the neighboring lines. Keep the literal in sync with `DEFAULT_WORKTREE_PATH_TEMPLATE` — a fork comment noting that is fine.)

In `gitfourchette/trtables.py`, in the pref-captions dict (near the `"externalDiff_help"` precedent at ~540):

```python
            "worktreePathTemplate": _("New worktree path template"),
            "worktreePathTemplate_help":
                "<p style='white-space: pre'>" + _("Path placeholders:") + "\n" + _tokenReferenceTable({
                    "$BASE_PATH": _("Repo root (main worktree)"),
                    "$BASE_ROOT": _("Parent directory of the repo root"),
                    "$REPO_NAME": _("Repo directory name"),
                    "$BRANCH": _("Branch name (slashes become dashes)"),
                }),
```

(Place both under whatever sub-dict holds `_category_git` keys — match how `gitPath`'s caption is keyed; if captions are one flat dict, append near the other `_help` entries.)

- [ ] **Step 5: Wire the dialog.** In `gitfourchette/forms/newworktreedialog.py`, add imports:

```python
from gitfourchette import settings
from gitfourchette.worktrees import DEFAULT_WORKTREE_PATH_TEMPLATE, renderWorktreePathTemplate
```

and replace `defaultPathForBranch` (currently builds `<parent>/<repoName>-<leaf>` by hand):

```python
    def defaultPathForBranch(self, branch: str) -> str:
        path = renderWorktreePathTemplate(
            settings.prefs.worktreePathTemplate, self._mainRoot, branch)
        if not path:  # blank template: fall back to the built-in default
            path = renderWorktreePathTemplate(
                DEFAULT_WORKTREE_PATH_TEMPLATE, self._mainRoot, branch)
        return path
```

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -q`
Expected: all pass (existing default-path expectations unchanged: the default template reproduces the old logic).

- [ ] **Step 7: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1089 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/worktrees.py gitfourchette/settings.py gitfourchette/trtables.py gitfourchette/forms/newworktreedialog.py test/test_worktrees.py
git commit -m "feat: worktree path template pref (\$BASE_PATH/\$BASE_ROOT/\$REPO_NAME/\$BRANCH)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: New worktree from a remote branch (B3)

**Files:**
- Modify: `gitfourchette/forms/newworktreedialog.py` (prefill semantics + remote base refs)
- Modify: `gitfourchette/tasks/worktreetasks.py` (param rename)
- Modify: `gitfourchette/sidebar/sidebar.py` (LocalBranch + RemoteBranch menu cases)
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: Tasks 2-4.
- Produces: `NewWorktree.flow(prefillRef: str = "")` — accepts a **full refname** (`refs/heads/x` or `refs/remotes/origin/x`; bare shorthand tolerated as a local); `NewWorktreeDialog(repo, prefillRef="", parent=None)`.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def testNewWorktreeFromRemoteBranch(tempDir, mainWindow):
    # origin/first-merge has NO local counterpart in the canned repo.
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    target = os.path.join(tempDir.name, "RemoteWT")

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/first-merge")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"new worktree here")
    dlg = findQDialog(rw, r"new worktree")
    assert dlg.wantNewBranch()
    assert dlg.newBranchName() == "first-merge"
    assert dlg.baseRef() == "origin/first-merge"
    dlg.setPath(target)
    dlg.accept()

    lb = rw.repo.branches.local["first-merge"]
    assert lb.upstream is not None
    assert lb.upstream.shorthand == "origin/first-merge"
    from gitfourchette import worktrees
    assert any(wt.branch == "refs/heads/first-merge" for wt in worktrees.listWorktrees(wd))


def testNewWorktreeFromRemoteBranchWithExistingLocal(tempDir, mainWindow):
    # local no-parent exists and is NOT checked out anywhere -> prefill existing mode.
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"new worktree here")
    dlg = findQDialog(rw, r"new worktree")
    assert not dlg.wantNewBranch()
    assert dlg.existingBranch() == "no-parent"
    dlg.reject()


def testRemoteBranchMenuHeldLocalShowsOpenInstead(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)  # holds no-parent

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/no-parent")
    menu = rw.sidebar.makeNodeMenu(node)
    assert findMenuAction(menu, r"open in.+worktree")
    with pytest.raises(KeyError):
        findMenuAction(menu, r"new worktree here")
```

(Before finalizing, run `git branch -a` in an unpacked canned repo to confirm `origin/first-merge` has no local counterpart and `origin/no-parent` exists; adjust ref names if reality differs — do not weaken assertions. `pytest` is imported in this test module already or add `import pytest` at the top.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -k "RemoteBranch" -v`
Expected: 3 FAIL (`KeyError: didn't find menu item 'new worktree here'`).

- [ ] **Step 3: Dialog prefill + remote base refs.** In `gitfourchette/forms/newworktreedialog.py`:

(a) Rename the constructor param: `def __init__(self, repo: Repo, prefillRef: str = "", parent=None):`

(b) After `localBranches = sorted(repo.branches.local)` add:

```python
        remoteBranches = sorted(b for b in repo.branches.remote if not b.endswith("/HEAD"))
```

and change the base-ref combo population to `self.baseRefCombo.addItems(localBranches + remoteBranches)` (the existing-branch combo stays local-only).

(c) Replace the prefill block (currently lines 41-43):

```python
        if prefillBranch and prefillBranch in localBranches:
            self.existingCombo.setCurrentText(prefillBranch)
        self.existingRadio.setChecked(True)
```

with:

```python
        prefillExisting = ""
        prefillNewName = ""
        prefillNewBase = ""
        if prefillRef:
            prefix, shorthand = RefPrefix.split(prefillRef)
            if prefix == RefPrefix.REMOTES:
                _remoteName, tail = split_remote_branch_shorthand(shorthand)
                if tail in localBranches:
                    # A same-name local exists: creating it again would be a
                    # guaranteed git failure — offer the local instead.
                    prefillExisting = tail
                else:
                    prefillNewName = tail
                    prefillNewBase = shorthand
            else:
                prefillExisting = shorthand  # refs/heads/x or bare shorthand

        if prefillExisting and prefillExisting in localBranches:
            self.existingCombo.setCurrentText(prefillExisting)
        self.existingRadio.setChecked(True)
        if prefillNewName:
            self.newRadio.setChecked(True)
            self.newNameEdit.setText(prefillNewName)
            self.baseRefCombo.setCurrentText(prefillNewBase)
```

(d) The default-path init a few lines below uses `self.existingCombo.currentText()` — make it honor the new-branch prefill:

```python
        initialBranchForPath = prefillNewName if prefillNewName else self.existingCombo.currentText()
        self.pathEdit.setText(self.defaultPathForBranch(initialBranchForPath))
```

(`RefPrefix` and `split_remote_branch_shorthand` come from the file's existing `from gitfourchette.porcelain import *`. This block runs BEFORE the signal wiring, so the `setChecked`/`setText` calls fire nothing — same reason the original prefill was safe.)

- [ ] **Step 4: Task param.** In `gitfourchette/tasks/worktreetasks.py`, rename `NewWorktree.flow`'s parameter:

```python
    def flow(self, prefillRef: str = ""):
        dlg = NewWorktreeDialog(self.repo, prefillRef, self.parentWidget())
```

(rest of the flow unchanged — `git worktree add -b <name> <path> origin/<x>` sets up tracking automatically when the start point is a remote-tracking ref).

- [ ] **Step 5: Sidebar menus.** In `gitfourchette/sidebar/sidebar.py`:

(a) LocalBranch case (~line 315): the existing entry passes `taskArgs=branchName` — change to `taskArgs=refName`:

```python
                *([TaskBook.action(self, NewWorktree, _("Checkout in New &Worktree…"), taskArgs=refName)]
                  if checkedOutWorktree is None else []),
```

(b) RemoteBranch case (~line 352): replace

```python
            worktreeActions = [self.openInWorktreeActionDef(localBranchWorktree)] if localBranchWorktree is not None else []
```

with:

```python
            worktreeActions = (
                [self.openInWorktreeActionDef(localBranchWorktree)]
                if localBranchWorktree is not None else
                [TaskBook.action(self, NewWorktree, _("New &Worktree Here…"), taskArgs=refName)])
```

(Mnemonic check, remote-branch menu: taken B/F/M/C/r/H/A — W is free. Verify rendered menu once via the test.)

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -q`
Expected: all pass (including the Task 2/3 tests — the menu-prefill path still yields `existingBranch() == "no-parent"`).

- [ ] **Step 7: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1092 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/forms/newworktreedialog.py gitfourchette/tasks/worktreetasks.py gitfourchette/sidebar/sidebar.py test/test_worktrees.py
git commit -m "feat: create worktree from a remote branch (tracking set up, 3-way prefill)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: MoveWorktree task (B5)

**Files:**
- Modify: `gitfourchette/tasks/worktreetasks.py` (new task)
- Modify: `gitfourchette/tasks/__init__.py` (extend worktreetasks block, alphabetized)
- Modify: `gitfourchette/tasks/taskbook.py` (`TaskBook.names` entry at alphabetical slot)
- Modify: `gitfourchette/sidebar/sidebar.py` (Worktree leaf menu)
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: `TextInputDialog` (`forms/textinputdialog.py:12` — `__init__(parent, title, label, ...)`, public `lineEdit`); `RemoveWorktree`'s guard idiom.
- Produces: `MoveWorktree(RepoTask)` with `flow(self, path: str)`; TaskBook name `tasks.MoveWorktree: _("Move worktree"),`.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def testMoveWorktree(tempDir, mainWindow):
    from gitfourchette.sidebar.sidebarmodel import SidebarItem
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    newPath = os.path.join(os.path.dirname(os.path.normpath(wd)), "MovedWT")

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"move worktree")
    dlg = findQDialog(rw, r"move worktree")
    dlg.lineEdit.setText(newPath)
    dlg.accept()

    assert not os.path.exists(linked)
    assert os.path.isdir(newPath)
    from gitfourchette import worktrees
    infos = worktrees.listWorktrees(wd)
    assert any(os.path.realpath(wt.path) == os.path.realpath(newPath) for wt in infos)
    assert rw.sidebar.countNodesByKind(SidebarItem.Worktree) == 2


def testMoveMainWorktreeBlocked(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    node = _worktreeNodeByPath(rw, wd)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"move worktree")
    acceptQMessageBox(rw, r"main worktree")
    assert os.path.isdir(os.path.normpath(wd))


def testMoveWorktreeOpenInTabBlocked(tempDir, mainWindow):
    wd, linked, rw = _openRepoWithLinkedWorktree(tempDir, mainWindow)
    mainWindow.openRepo(linked)
    mainWindow.tabs.setCurrentIndex(0)

    node = _worktreeNodeByPath(rw, linked)
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"move worktree")
    acceptQMessageBox(rw, r"close.+tab")
    assert os.path.isdir(linked)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -k "MoveWorktree or MoveMain" -v`
Expected: 3 FAIL (`KeyError: didn't find menu item 'move worktree'`).

- [ ] **Step 3: Implement the task.** In `gitfourchette/tasks/worktreetasks.py`, add the import at the top (with the other form imports):

```python
from gitfourchette.forms.textinputdialog import TextInputDialog
```

and add the class between `NewWorktree` and `RemoveWorktree` (keep source order readable; registration order is what must be alphabetical):

```python
class MoveWorktree(RepoTask):
    def flow(self, path: str):
        mainInfo = next((wt for wt in self.repoModel.worktrees if wt.isMain), None)
        if mainInfo is not None and os.path.realpath(path) == os.path.realpath(mainInfo.path):
            raise AbortTask(_("You can’t move the main worktree."), icon="information")

        from gitfourchette.application import GFApplication
        mainWindow = GFApplication.instance().mainWindow
        if mainWindow is not None and mainWindow.tabWidgetForWorkdirPath(path) is not None:
            raise AbortTask(
                _("This worktree is open in a tab. Close its tab before moving it."),
                icon="information")

        dlg = TextInputDialog(
            self.parentWidget(),
            _("Move worktree"),
            _("Move worktree {0} to:", bquo(compactPath(path))))
        dlg.lineEdit.setText(path)
        yield from self.flowDialog(dlg)
        newPath = dlg.lineEdit.text().strip()
        dlg.deleteLater()

        driver = yield from self.flowCallGit("worktree", "move", path, newPath, autoFail=False)
        if driver.exitCode() != 0:
            raise AbortTask(driver.htmlErrorText())

        self.epilog.effects |= TaskEffects.Refs
```

(Match `RemoveWorktree`'s import placement style for `GFApplication` — it does the local import inside `flow`. A locked worktree makes `git worktree move` fail; its stderr surfaces via the `AbortTask` — spec-accepted.)

- [ ] **Step 4: Register.** `gitfourchette/tasks/__init__.py`, worktreetasks block becomes (alphabetized):

```python
from gitfourchette.tasks.worktreetasks import (
    MoveWorktree,
    NewWorktree,
    PruneWorktrees,
    RemoveWorktree,
)
```

`gitfourchette/tasks/taskbook.py`, `TaskBook.names`, at the alphabetical slot (right before the `New*` entries, after any `M…` entries such as `MergeBranch`):

```python
            tasks.MoveWorktree: _("Move worktree"),
```

- [ ] **Step 5: Menu entry.** In `gitfourchette/sidebar/sidebar.py`, Worktree leaf case, insert before the `RemoveWorktree` entry (after the separator):

```python
                TaskBook.action(self, MoveWorktree, accel="M", taskArgs=data),
```

(`accel="M"` renders `&Move worktree…`. Leaf-menu mnemonics now O/F/P/M/R — unique. Add `MoveWorktree` to sidebar.py's task imports next to `NewWorktree`/`RemoveWorktree`.)

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -q`
Expected: all pass.

- [ ] **Step 7: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1095 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tasks/worktreetasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/sidebar/sidebar.py test/test_worktrees.py
git commit -m "feat: MoveWorktree task (git worktree move, main/tab guards)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: "Commit and Push" dialog caption (D10)

**Files:**
- Modify: `gitfourchette/tasks/committasks.py` (`NewCommit.flow` — optional caption param)
- Modify: `gitfourchette/tasks/commitpushtasks.py` (pass the caption)
- Test: `test/test_shiftbuttons.py` (append)

**Interfaces:**
- Consumes: `CommitDialog.acceptButton` (@property, `commitdialog.py:18-20`); `flowSubtask` kwargs forwarding.
- Produces: `NewCommit.flow(self, buttonCaption: str = "")` — default preserves upstream behavior everywhere.

- [ ] **Step 1: Write the failing test** — append to `test/test_shiftbuttons.py`:

```python
def testCommitAndPushDialogCaption(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    writeFile(f"{wd}/pushme.txt", "and push me now")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    assert dialog.acceptButton.text() == "Co&mmit and Push"
    assert dialog.windowTitle() == "Commit and Push"
    dialog.reject()

    # Plain commit dialog is unaffected
    NewCommit.invoke(rw)
    dialog2: CommitDialog = findQDialog(rw, "commit")
    assert dialog2.acceptButton.text() == "Co&mmit"
    assert dialog2.windowTitle() != "Commit and Push"
    dialog2.reject()
```

(Add `NewCommit` to this file's `from gitfourchette.tasks import ...` line. Rejecting the first dialog aborts CommitAndPush cleanly — pinned by the existing cancel test — so the staged file is still staged for the second dialog.)

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_shiftbuttons.py -k Caption -v`
Expected: FAIL — button text is `Co&mmit`.

- [ ] **Step 3: Implement.** In `gitfourchette/tasks/committasks.py`:

(a) `def flow(self):` (line 35) becomes:

```python
    def flow(self, buttonCaption: str = ""):
```

(b) After the `CommitDialog(...)` construction (line ~77), before `cd.setWindowModality(...)`:

```python
        if buttonCaption:  # Fork: e.g. "Commit and Push" (Shift+Commit)
            cd.acceptButton.setText(buttonCaption)
            cd.setWindowTitle(stripAccelerators(buttonCaption))
```

(Check `stripAccelerators` is importable in committasks.py — it lives in toolbox and the file star-imports toolbox; if not, strip with `buttonCaption.replace("&", "")`.)

(c) In `gitfourchette/tasks/commitpushtasks.py`, the subtask call becomes:

```python
        yield from self.flowSubtask(NewCommit, buttonCaption=_("Co&mmit and Push"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_shiftbuttons.py -q`
Expected: all pass.

- [ ] **Step 5: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1096 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/tasks/committasks.py gitfourchette/tasks/commitpushtasks.py test/test_shiftbuttons.py
git commit -m "feat: commit dialog says Commit and Push when Shift-invoked

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Tabs — same-repo adjacency + plain titles (C8, C9)

**Files:**
- Modify: `gitfourchette/mainwindow.py` (`_openRepo` hook; `refreshAllTabTexts` simplification)
- Modify: `gitfourchette/toolbox/pathutils.py` (delete `disambiguateTabTitlesByPath`)
- Modify: `gitfourchette/toolbox/__init__.py:37` (drop the export)
- Test: `test/test_worktrees.py` (append)

**Interfaces:**
- Consumes: `tabcolors.repoBindingKey(workdir)` (already imported in mainwindow.py).
- Produces: behavior only.

- [ ] **Step 1: Write the failing tests** — append to `test/test_worktrees.py`:

```python
def testNewTabOpensAdjacentToSameRepoSiblings(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT no-parent", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    otherWd = unpackRepo(tempDir, renameTo="UnrelatedRepo")

    mainWindow.openRepo(wd)
    mainWindow.openRepo(otherWd)
    mainWindow.openRepo(linked)  # default placement -> after its sibling, not at the end

    order = [os.path.realpath(w.workdir) for w in mainWindow.tabs.widgets()]
    assert order == [os.path.realpath(p) for p in (wd, linked, otherWd)]


def testTabTitlesStayPlainBasenames(tempDir, mainWindow):
    # Fork: duplicate-basename tabs are NOT disambiguated with parent paths --
    # tab colors and the [M] marker carry the distinction (user decision).
    wd1 = unpackRepo(tempDir)
    sub = os.path.join(tempDir.name, "elsewhere")
    os.makedirs(sub)
    wd2 = unpackRepo(sub)

    mainWindow.openRepo(wd1)
    mainWindow.openRepo(wd2)

    for i in range(mainWindow.tabs.count()):
        assert mainWindow.tabs.tabs.tabText(i) == "TestGitRepository"
```

(If offscreen elision ever garbles the equality assert, compare `mainWindow.tabs.tabs.shadowText[i]` instead — the unelided bookkeeping list, `qtabwidget2.py:135`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -k "AdjacentTo or PlainBasenames" -v`
Expected: adjacency FAILS (linked lands at the end); titles FAILS (disambiguated `…/TestGitRepository` forms).

- [ ] **Step 3: Adjacency hook.** In `gitfourchette/mainwindow.py`, `_openRepo`, right before `stub = RepoStub(...)` / the `insertTab` block:

```python
        # Fork: cluster same-repo tabs — a new tab whose repo shares a main
        # worktree with an existing tab inserts after the last such sibling.
        # An explicit tabIndex (e.g. openRepoNextTo) always wins.
        if tabIndex < 0:
            bindingKey = tabcolors.repoBindingKey(path)
            siblings = [i for i, w in enumerate(self.tabs.widgets())
                        if tabcolors.repoBindingKey(w.workdir) == bindingKey]
            if siblings:
                tabIndex = siblings[-1] + 1
```

- [ ] **Step 4: Plain titles.** In `gitfourchette/mainwindow.py`, replace the whole body of `refreshAllTabTexts` (lines ~935-961) with:

```python
    def refreshAllTabTexts(self):
        # Fork: titles stay plain basenames/nicknames — no parent-path
        # disambiguation for duplicate names (tab colors + [M] marker
        # carry the distinction).
        for i, widget in enumerate(self.tabs.widgets()):
            self.tabs.setTabText(i, escamp(widget.getTitle()))
        self.refreshTabColors()
```

Delete `disambiguateTabTitlesByPath` from `gitfourchette/toolbox/pathutils.py:30-51` and remove it from the `toolbox/__init__.py:37` import line. (Verified: mainwindow.py:954 was the only caller; no test references it. Ruff will flag any leftover.)

- [ ] **Step 5: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_worktrees.py -q`
Expected: all pass (the `[M]` tab tests at ~519-547 use `startswith`/prefix asserts and don't depend on disambiguation).

- [ ] **Step 6: Full suite + ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1098 passed, 16 skipped, 0 failed. (If a test elsewhere pinned disambiguated titles, adapt it to plain basenames — spec-mandated behavior change.)
Run: `.venv/bin/python -m ruff check` → All checks passed.

- [ ] **Step 7: Commit**

```bash
git add gitfourchette/mainwindow.py gitfourchette/toolbox/pathutils.py gitfourchette/toolbox/__init__.py test/test_worktrees.py
git commit -m "feat: same-repo tab adjacency; plain tab titles (drop path disambiguation)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Stash single-file pin test + integration pass

**Files:**
- Test: `test/test_tasks_stash.py` (append)
- No product code.

**Interfaces:**
- Consumes: upstream `CommittedFiles` restore action (verified working this session).
- Produces: regression pin for a user-valued behavior.

- [ ] **Step 1: Write the pin test** — append to `test/test_tasks_stash.py`:

```python
def testRestoreSingleFileFromStash(tempDir, mainWindow):
    # Forkette pin: applying a SINGLE file from a stash works via the stash's
    # file list -> Restore File Revision -> As Of This Commit. (Fork-parity
    # behavior the fork relies on; upstream feature, pinned here on purpose.)
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/a/a1.txt", "STASHED CONTENT\n")
    writeFile(f"{wd}/b/b1.txt", "OTHER STASHED FILE\n")
    runShellScript("git stash push -m probe", wd)
    rw = mainWindow.openRepo(wd)

    assert readFile(f"{wd}/a/a1.txt").decode() != "STASHED CONTENT\n"

    rw.selectRef("refs/stash")
    assert "a/a1.txt" in qlvGetRowData(rw.committedFiles)
    qlvClickNthRow(rw.committedFiles, 0)  # a/a1.txt

    menu = rw.committedFiles.makeContextMenu()
    triggerMenuAction(menu, r"restore/as of this commit")
    acceptQMessageBox(rw, r"restore|workdir|working")

    assert readFile(f"{wd}/a/a1.txt").decode() == "STASHED CONTENT\n"
    # Only that one file was applied:
    assert readFile(f"{wd}/b/b1.txt").decode() != "OTHER STASHED FILE\n"
```

(If `readFile` isn't in `test/util.py`, use `open(...).read()` — match the file's existing idiom. The menu path and box regex were validated empirically this session.)

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_stash.py -k RestoreSingleFile -v`
Expected: PASS immediately (it pins existing behavior — no red step here by design).

- [ ] **Step 3: Full suite + ruff + sanity import**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` → expect 1099 passed, 16 skipped, 0 failed.
Run: `.venv/bin/python -m ruff check` → All checks passed.
Run: `.venv/bin/python -c "import gitfourchette; print(gitfourchette.__version__)"` → prints `1.9.1+fork` (or current).

- [ ] **Step 4: Commit**

```bash
git add test/test_tasks_stash.py
git commit -m "test: pin single-file restore from a stash

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## After all tasks

- Final whole-branch review (superpowers:requesting-code-review) on the most capable model, fed the Minor-findings roll-up from task reviews. Special attention: the quiet-switch boundary (submodule dialog kept, detached/held/clobber boxes intact), upstream-merge cleanliness of the three upstream-file edits (`branchtasks.py`, `committasks.py`, `mainwindow.py`), the `repoBindingKey` call cost in `_openRepo` (one-time per tab open — fine), and prefill interplay between Tasks 3/4/5 in `newworktreedialog.py`.
- Merge flow: merge `fork-main` into the branch, combined suite in the worktree, `git merge --ff-only` in the main checkout when clean.
- Update the ledger (`.superpowers/sdd/progress.md`) with the batch outcome.
- Manual GUI smoke (user): quiet switch feel on gitfourchette + beans repos, submodule repo still confirms, new-worktree tab opens directly, remote-branch → New Worktree Here (tracking set), path template with `$BASE_PATH-worktrees/$BRANCH`, move worktree, dialog width/radio feel, same-repo tab clustering, plain tab titles on beans-api/beans-app, Shift+Commit button caption.
