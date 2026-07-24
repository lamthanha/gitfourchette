# UX Quick Wins + Starred Branches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five Fork-parity UX features: copy branch name from the sidebar, quiet fetch (no modal progress dialog), sidebar collapse defaults (tags + non-tracked remotes), a rename-remote-branch checkbox on local rename, and starred branches under a "Starred" sidebar group.

**Architecture:** No new tasks, dialogs, or modules — every feature extends existing machinery: `ActionDef` entries and a toggle method in `sidebar.py`, `broadcastProcesses()` overrides in `nettasks.py`, two new `RepoPrefs` fields, a priming hook at the existing collapse-cache load site in `repowidget.py`, an optional parameter on `RenameRemoteBranch` chained via `flowSubtask`, and alias nodes in `sidebarmodel.py` that deliberately stay out of `nodesByRef`.

**Tech Stack:** Python ≥3.10, PyQt6, pygit2 (reads; local rename via existing porcelain call), pytest + pytest-qt.

## Global Constraints

- Repo: `/home/admin/workspace.personal/gitfourchette`, branch `fork-main`. Spec: `docs/superpowers/specs/2026-07-25-ux-quickwins-starred-design.md`.
- Test runner prefix (always): `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`.
- Every user-facing string via `_("...")` / `_n(...)`; typographic `…` and `’`.
- **This plan adds NO task registrations** — no edits to `tasks/__init__.py` or `taskbook.py`. This keeps it conflict-free with the `feat/multiselect-rebase` branch executing in parallel (disjoint files: that branch touches `rebasetasks.py`, `rebasetododialog.py`, `graphview.py`, taskbook/init).
- Sidebar menu mnemonics in use — local-branch menu: `&S`witch, `&M`erge, `&o`nto, `&F`etch, Pu`&l`l, `&P`ush, `&U`pstream, Re`&n`ame, `&D`elete, New `&B`ranch, `&H`ide, Hide `&A`ll. New entries use `&C`opy and Sta`&r`/Unsta`&r` — before committing each menu change, verify the letter is unique within that menu block (remote-branch block uses task-default captions for rename/delete; check them).
- Collapse-cache keys are `SidebarNode.getCollapseHash()` = `f"{kind.name}.{data}"` (e.g. `"Remote.origin"`, `"TagsHeader."`). Never hash with Python `hash()`.
- `nodesByRef` is last-write-wins. Starred alias nodes MUST NOT be registered in it — canonical nodes stay authoritative for `findNodeByRef`/`indexForRef`/jump.
- RepoPrefs persistence: mutate the field, then `prefs.setDirty()`; `PrefsFile.write()` handles serialization to `.git/gitfourchette.json` (sets encode to lists; fields equal to their dataclass default are skipped).
- Behavior invariant: quiet fetch must not swallow errors — failed fetch still surfaces the task-error dialog; only the `processStarted` broadcast is suppressed.
- Deliberate default-behavior change in Task 4 (collapse priming): existing `test/test_sidebar.py` tests that assume an all-expanded initial tree may legitimately need minimal updates — each such edit must be listed and justified in the task report. Never touch an assertion unrelated to initial expansion state.
- TDD: failing test first. Commit per task with trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Key verified facts (fork tree at 5e5b47da)

- Sidebar enum is `SidebarItem` (`sidebarmodel.py:31-49`); root section order = `SidebarLayout.RootItems` (`sidebarmodel.py:53-66`), consumed verbatim in `rebuild()` (`:340-342`); layout/behavior sets at `:72-101`.
- `SidebarNode` fields: `children, parent, row, kind, data, warning, displayName`; ctor `SidebarNode(kind, data="")`; `getCollapseHash()` at `:145-150`.
- `rebuild()` reaches prefs via `repoModel.prefs` (it already reads `repoModel.prefs.sortRemoteBranches` at `:441`).
- Collapse load site: `repowidget.py:225-230` (`collapseCache = repoModel.prefs.collapseCache; if collapseCache: ...update...; self.sidebar.refresh(repoModel)`).
- `Sidebar.copyToClipboard(text)` (`sidebar.py:1017-1019`) copies + emits the status toast.
- Local-branch menu block: `sidebar.py:196-313`; remote-branch block `:318-372`; remote block `:374-427` with `Copy Remote &URL` at `:409`.
- `ProcessDialog`: single persistent instance `rw.processDialog` (`repowidget.py:89`), popped only via `taskRunner.processStarted`, which is gated by `task.broadcastProcesses()` (`repotask.py:1018-1024`). Status-bar busy message is emitted unconditionally (`repotask.py:1015-1016`). `AutoFetchRemotes` (`nettasks.py:195-197`) and `PushBranch` (`:355-356`) already override to `False`.
- Under `RepoTaskRunner.ForceSerial` (default in tests) the pop-up timer never fires; to observe dialog behavior use the `taskThread` fixture (`conftest.py:263-270`) + `DelayGitCommandContext` — pattern: `testGitProcessStuck` (`test_gitfourchette.py:940-965`).
- `TextInputDialog.setExtraWidget(widget)` (`textinputdialog.py:77-79`) — row 2 of the grid is reserved for exactly this; currently unused anywhere.
- `RenameRemoteBranch.flow(remoteBranchShorthand)` (`nettasks.py:95-162`): dialog → safety `flowSubtask(FetchRemoteBranch, oldShorthand)` → atomic push of 2 refspecs → retargets every local branch whose `upstream_name` matched. `RenameBranch` (`branchtasks.py:79-114`) renames via `repo.rename_local_branch` on a worker thread.
- `nettasks.py` imports from `branchtasks.py` (PullBranch chains MergeBranch) — so `branchtasks` must import `RenameRemoteBranch` LOCALLY inside the flow to avoid a circular import.
- Tracked-remote lookup precedent: `repo.branches.local[repo.head_branch_shorthand].upstream.remote_name` (`submoduletasks.py:41-44`).
- Test helpers: `rw.sidebar.findNodeByRef/findNodeByKind/findNodesByKind/findNode(lambda)`, `nodeToFilterIndex`, `sb.isExpanded(index)`; clipboard asserted via `QApplication.clipboard().text()` (conftest clears it per test); `makeBareCopy(wd, addAsRemote="localfs", preFetch=True)` sets up a file remote with upstreams.

---

### Task 1: Copy branch name

**Files:**
- Modify: `gitfourchette/sidebar/sidebar.py` (local-branch menu block ~line 196-313; remote-branch block ~318-372)
- Test: `test/test_sidebar.py` (append)

**Interfaces:**
- Consumes: existing `self.copyToClipboard(text)` (`sidebar.py:1017`); block-local variables `branchName` (local block) and the remote-branch block's shorthand variable (verify its name in the block — it derives from `RefPrefix.split(data)`).
- Produces: menu entry "&Copy Branch Name" on both node kinds.

- [ ] **Step 1: Write the failing test**

Append to `test/test_sidebar.py`:

```python
def testCopyBranchName(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"copy branch name")
    assert QApplication.clipboard().text() == "master"

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"copy branch name")
    assert QApplication.clipboard().text() == "origin/master"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py::testCopyBranchName -x -q`
Expected: FAIL — no menu item matches.

- [ ] **Step 3: Add the entries**

In the local-branch block, directly after the `NewBranchFromRef` action (`_("New &Branch Here…")`), insert:

```python
                ActionDef(_("&Copy Branch Name"), lambda: self.copyToClipboard(branchName)),
```

In the remote-branch block, insert the same entry before the `&Hide in Graph` action, passing the block's existing `"remote/branch"` shorthand variable (the one obtained from `RefPrefix.split(data)` — use its actual name in that block):

```python
                ActionDef(_("&Copy Branch Name"), lambda: self.copyToClipboard(shorthand)),
```

Verify `&C` is unique in each block (check the remote-branch block's task-default captions for Rename/Delete; if `&C` collides there, use `Copy Branch &Name` (`&N`) in that block only and adjust nothing else).

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py::testCopyBranchName -x -q`
Expected: PASS.

- [ ] **Step 5: Sidebar suite regression + commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -q`
Expected: all PASS.

```bash
git add gitfourchette/sidebar/sidebar.py test/test_sidebar.py
git commit -m "feat: copy branch name from sidebar context menu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Quiet fetch

**Files:**
- Modify: `gitfourchette/tasks/nettasks.py` (`FetchRemotes` ~line 166, `FetchRemoteBranch` ~line 238)
- Test: `test/test_tasks_net.py` (append)

**Interfaces:**
- Consumes: `broadcastProcesses()` gate (`repotask.py:1018-1024`); `taskThread` fixture + `DelayGitCommandContext` (pattern: `test_gitfourchette.py:940-965`); `rw.processDialog` (persistent `ProcessDialog` instance).
- Produces: `FetchRemotes.broadcastProcesses() -> False`, `FetchRemoteBranch.broadcastProcesses() -> False`.

- [ ] **Step 1: Write the failing test**

Append to `test/test_tasks_net.py`. The integration test mirrors `testGitProcessStuck`'s harness (`test_gitfourchette.py:940-965`) — copy its `taskThread` + `DelayGitCommandContext` structure, adapted to fetch; keep the same waiting helpers it uses:

```python
def testFetchShowsNoProcessDialog(tempDir, mainWindow, taskThread):
    from gitfourchette.forms.processdialog import ProcessDialog

    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True, deleteOtherRemotes=True)
    rw = mainWindow.openRepo(wd)

    # Delay the git process long enough for ProcessDialog's pop-up timer
    # (300ms) to fire if it were going to -- mirror testGitProcessStuck's
    # DelayGitCommandContext usage and waiting pattern exactly.
    with DelayGitCommandContext(mainWindow) as delay:
        node = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "localfs")
        triggerMenuAction(rw.sidebar.makeNodeMenu(node), "fetch")
        QTest.qWait(600)  # > PopUpDelay while the process is held
        assert not rw.processDialog.isVisible()
    waitUntilTrue(lambda: not rw.taskRunner.isBusy())
    assert not rw.processDialog.isVisible()
```

(Adapt the context-manager/waiting details to whatever `testGitProcessStuck` actually does — the assertions to keep are: dialog not visible while the delayed fetch runs, and not visible after. If `DelayGitCommandContext` needs different arguments, follow that test.)

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_net.py::testFetchShowsNoProcessDialog -x -q`
Expected: FAIL — the dialog becomes visible ~300ms into the held fetch. (If the harness adaptation itself errors, fix the harness first so the test fails on the visibility assert specifically.)

- [ ] **Step 3: Add the overrides**

In `nettasks.py`, add to `FetchRemotes` and `FetchRemoteBranch` (same shape as `AutoFetchRemotes`, `nettasks.py:195-197`):

```python
    def broadcastProcesses(self) -> bool:
        # Fork-style quiet fetch: status-bar busy indicator only, no modal ProcessDialog.
        return False
```

- [ ] **Step 4: Run the new test + fetch regression**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_net.py -q`
Expected: all PASS (existing `testFetchRemote`/`testFetchRemoteBranch` assert status-bar text and repo state — unaffected by the suppressed dialog; the error path stays covered by existing failing-fetch tests in that file, which run through the task-error dialog, not ProcessDialog).

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/tasks/nettasks.py test/test_tasks_net.py
git commit -m "feat: quiet fetch -- suppress modal progress dialog, keep statusbar busy indicator

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Rename remote branch with local rename

**Files:**
- Modify: `gitfourchette/tasks/nettasks.py` (`RenameRemoteBranch.flow`, lines ~95-162)
- Modify: `gitfourchette/tasks/branchtasks.py` (`RenameBranch.flow`, lines ~79-114)
- Test: `test/test_tasks_branch.py` (append)

**Interfaces:**
- Consumes: `TextInputDialog.setExtraWidget(widget)` (`textinputdialog.py:77-79`); `flowSubtask` chaining idiom (`RenameRemoteBranch` itself uses it at `nettasks.py:145`).
- Produces: `RenameRemoteBranch.flow(self, remoteBranchShorthand: str, newBranchName: str = "")` — empty `newBranchName` keeps today's interactive behavior exactly; non-empty skips the dialog and pushes directly.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_tasks_branch.py`:

```python
def testRenameBranchAlsoRenamesRemoteBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    barePath = makeBareCopy(wd, addAsRemote="localfs", preFetch=True, deleteOtherRemotes=True)
    rw = mainWindow.openRepo(wd)
    assert rw.repo.branches.local["no-parent"].upstream_name == "refs/remotes/localfs/no-parent"

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^re.name")

    dlg = findQDialog(rw, r"rename.+branch")
    checkbox: QCheckBox = dlg.findChild(QCheckBox)
    assert checkbox is not None
    assert re.search(r"also rename.+localfs/no-parent", checkbox.text(), re.I)
    assert not checkbox.isChecked()  # default off: no surprise network push
    checkbox.setChecked(True)
    dlg.findChild(QLineEdit).setText("renamed-both")
    dlg.accept()

    assert "renamed-both" in rw.repo.branches.local
    assert "no-parent" not in rw.repo.branches.local
    assert "localfs/renamed-both" in rw.repo.branches.remote
    assert "localfs/no-parent" not in rw.repo.branches.remote
    assert rw.repo.branches.local["renamed-both"].upstream_name == "refs/remotes/localfs/renamed-both"
    with RepoContext(barePath) as bareRepo:
        assert "renamed-both" in bareRepo.branches.local
        assert "no-parent" not in bareRepo.branches.local


def testRenameBranchUncheckedLeavesRemoteAlone(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True, deleteOtherRemotes=True)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^re.name")
    dlg = findQDialog(rw, r"rename.+branch")
    assert not dlg.findChild(QCheckBox).isChecked()
    dlg.findChild(QLineEdit).setText("local-only")
    dlg.accept()

    assert "local-only" in rw.repo.branches.local
    assert "localfs/no-parent" in rw.repo.branches.remote
    # Local rename preserves the upstream config, still pointing at the old remote branch
    assert rw.repo.branches.local["local-only"].upstream_name == "refs/remotes/localfs/no-parent"


def testRenameBranchWithoutUpstreamHasNoCheckbox(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git branch lonely", wd)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/lonely")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^re.name")
    dlg = findQDialog(rw, r"rename.+branch")
    assert dlg.findChild(QCheckBox) is None
    dlg.reject()
```

(`re`, `QCheckBox`, `QLineEdit`, `RepoContext` are already available in this test module via its existing imports — verify and extend the import line only if missing.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_branch.py -x -q -k "AlsoRenames or LeavesRemoteAlone or NoCheckbox"`
Expected: first two FAIL (`findChild(QCheckBox)` returns None); the third may already pass.

- [ ] **Step 3: Make `RenameRemoteBranch` optionally non-interactive**

In `nettasks.py`, change the signature and wrap ONLY the dialog block:

```python
    def flow(self, remoteBranchShorthand: str, newBranchName: str = ""):
```

```python
        if not newBranchName:
            reservedNames = self.repo.listall_remote_branches().get(remoteName, [])
            with suppress(ValueError):
                reservedNames.remove(branchName)
            nameTaken = _("This name is already taken by another branch on this remote.")

            dlg = TextInputDialog(...)          # existing dialog block, unchanged
            ...
            yield from self.flowDialog(dlg)
            dlg.deleteLater()
            newBranchName = dlg.lineEdit.text()
```

Everything after (adjustUpstreams collection, safety fetch subtask, atomic push, upstream retarget, status) runs unchanged for both modes. Keep the existing `newBranchName = branchName` prefill line inside the interactive block (it seeds the dialog only).

- [ ] **Step 4: Add the checkbox to `RenameBranch`**

In `branchtasks.py`, `RenameBranch.flow`, after the dialog is constructed (before `flowDialog`):

```python
        upstream = None
        renameRemoteCheckbox = None
        with suppress(KeyError):
            upstream = self.repo.branches.local[oldBranchName].upstream
        if upstream is not None:
            renameRemoteCheckbox = QCheckBox(
                _("Also rename {0} on the remote", lquoe(upstream.shorthand)))
            renameRemoteCheckbox.setChecked(False)
            dlg.setExtraWidget(renameRemoteCheckbox)
```

And after the existing local rename + status line, chain the remote rename (note the local import — `nettasks` imports from `branchtasks`, so the reverse import must be deferred to avoid a cycle):

```python
        yield from self.flowEnterUiThread()
        if renameRemoteCheckbox is not None and renameRemoteCheckbox.isChecked():
            from gitfourchette.tasks.nettasks import RenameRemoteBranch
            yield from self.flowSubtask(RenameRemoteBranch, upstream.shorthand, newBranchName)
```

(The existing flow ends on the worker thread after `rename_local_branch`; the `flowEnterUiThread()` hop is required before `flowSubtask`. If the remote push fails, the subtask's error surfaces normally and the local rename stands — per spec, no rollback. A name collision on the remote is caught by the atomic push failing; the local-name validator already ran.)

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_branch.py -q -k Rename`
Expected: all Rename tests PASS, including the pre-existing `testRenameBranch` and `test_tasks_net.py::testRenameRemoteBranch` unchanged behavior — run that too:

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tasks_net.py::testRenameRemoteBranch -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gitfourchette/tasks/nettasks.py gitfourchette/tasks/branchtasks.py test/test_tasks_branch.py
git commit -m "feat: optionally rename remote branch together with local rename

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Sidebar collapse defaults

**Files:**
- Modify: `gitfourchette/repoprefs.py` (add `collapsePrimed` field, next to `collapseCache` at line ~35)
- Modify: `gitfourchette/sidebar/sidebarmodel.py` (add module-level `defaultCollapseCache`)
- Modify: `gitfourchette/repowidget.py` (priming at the load site, lines ~225-230)
- Test: `test/test_sidebar.py` (append + adapt affected tests)

**Interfaces:**
- Consumes: `getCollapseHash` key format `f"{kind.name}.{data}"`; load site `repowidget.py:225-230`; tracked-remote idiom `repo.branches.local[repo.head_branch_shorthand].upstream.remote_name`.
- Produces: `RepoPrefs.collapsePrimed: bool = False`; `defaultCollapseCache(repoModel) -> set[str]` in `sidebarmodel.py`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_sidebar.py`:

```python
def _sbExpanded(rw, node):
    return rw.sidebar.isExpanded(rw.sidebar.nodeToFilterIndex(node))


def testSidebarCollapseDefaults(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)  # origin (canned) + localfs
    runShellScript("git branch --set-upstream-to=origin/master master", wd)
    rw = mainWindow.openRepo(wd)

    origin = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "origin")
    localfs = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "localfs")
    tags = rw.sidebar.findNodeByKind(SidebarItem.TagsHeader)
    branches = rw.sidebar.findNodeByKind(SidebarItem.LocalBranchesHeader)
    remotesRoot = rw.sidebar.findNodeByKind(SidebarItem.RemotesHeader)

    assert _sbExpanded(rw, origin)          # tracked remote stays open
    assert not _sbExpanded(rw, localfs)     # other remote collapsed
    assert not _sbExpanded(rw, tags)        # tags collapsed
    assert _sbExpanded(rw, branches)        # untouched sections stay expanded
    assert _sbExpanded(rw, remotesRoot)     # remotes ROOT stays open (names visible)


def testSidebarCollapseDefaultsPrimeOnlyOnce(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    runShellScript("git branch --set-upstream-to=origin/master master", wd)
    rw = mainWindow.openRepo(wd)

    # User expands everything the defaults collapsed...
    for node in [rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "localfs"),
                 rw.sidebar.findNodeByKind(SidebarItem.TagsHeader)]:
        rw.sidebar.expand(rw.sidebar.nodeToFilterIndex(node))

    mainWindow.closeTab(0)
    rw = mainWindow.openRepo(wd)

    # ...and is NOT re-collapsed on the next open
    localfs = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "localfs")
    tags = rw.sidebar.findNodeByKind(SidebarItem.TagsHeader)
    assert _sbExpanded(rw, localfs)
    assert _sbExpanded(rw, tags)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -x -q -k CollapseDefaults`
Expected: `testSidebarCollapseDefaults` FAILs (`localfs`/`tags` are expanded today).

- [ ] **Step 3: Add the prefs field and the default computer**

`repoprefs.py`, next to `collapseCache`:

```python
    collapsePrimed: bool = False
```

`sidebarmodel.py`, module level (near the top, after the enum definitions):

```python
def defaultCollapseCache(repoModel) -> set[str]:
    """Collapse hashes to prime a repo whose sidebar was never opened before:
    tags and every remote's subtree, except the tracked remote's (the current
    branch's upstream remote; falling back to 'origin', then the first remote)."""
    from contextlib import suppress

    remotes = list(repoModel.remotes)
    tracked = ""
    with suppress(KeyError, AttributeError, GitError):
        repo = repoModel.repo
        upstream = repo.branches.local[repo.head_branch_shorthand].upstream
        if upstream is not None:
            tracked = upstream.remote_name
    if not tracked:
        tracked = "origin" if "origin" in remotes else (remotes[0] if remotes else "")

    hashes = {f"{SidebarItem.TagsHeader.name}."}
    hashes |= {f"{SidebarItem.Remote.name}.{name}" for name in remotes if name != tracked}
    return hashes
```

(`GitError` comes from the existing porcelain star import in that module; if it isn't in scope, drop it from the suppress tuple.)

- [ ] **Step 4: Prime at the load site**

In `repowidget.py`, replace the collapse-cache load block (lines ~225-230) with:

```python
        with QSignalBlockerContext(self.sidebar):
            prefs = repoModel.prefs
            if not prefs.collapsePrimed:
                prefs.collapseCache.update(defaultCollapseCache(repoModel))
                prefs.collapsePrimed = True
                prefs.setDirty()
            if prefs.collapseCache:
                self.sidebar.sidebarModel.collapseCache.update(prefs.collapseCache)
            self.sidebar.refresh(repoModel)
```

Add `defaultCollapseCache` to repowidget's existing sidebar imports.

- [ ] **Step 5: Run the sidebar suite; adapt legitimately-broken tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -q`
Some pre-existing tests assume the old all-expanded default (candidates: `testSidebarCollapsePersistent`, `testSidebarCollapseExpandAllFolders`, `testSidebarFilterCollapseState`). For each failure: if it asserts the OLD default initial state, minimally adapt (e.g. explicitly expand the relevant node after `openRepo`, or pre-set the prefs state the test needs via `rw.sidebar.sidebarModel.repoModel.prefs`); anything else is a regression to fix in product code. List every adapted test with one-line justification in the task report.
Expected after adaptation: all PASS.

- [ ] **Step 6: Cross-suite spot check + commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py test/test_tasks_branch.py test/test_tasks_net.py -q`
Expected: all PASS.

```bash
git add gitfourchette/repoprefs.py gitfourchette/sidebar/sidebarmodel.py gitfourchette/repowidget.py test/test_sidebar.py
git commit -m "feat: collapse tags and non-tracked remotes by default in sidebar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Starred branches

**Files:**
- Modify: `gitfourchette/repoprefs.py` (add `starredRefs`)
- Modify: `gitfourchette/sidebar/sidebarmodel.py` (enum member, RootItems, layout sets, rebuild population)
- Modify: `gitfourchette/sidebar/sidebar.py` (toggle method + menu entries in local- and remote-branch blocks)
- Test: `test/test_sidebar.py` (append)

**Interfaces:**
- Consumes: `SidebarNode(kind, data)`, `rootNode.findChild`, `nodesByRef` (read-only for aliases!), `repoModel.prefs`, `wantHideNode`'s refresh mechanism (mirror it).
- Produces: `RepoPrefs.starredRefs: set`; `SidebarItem.StarredHeader`; `Sidebar.wantToggleStarNode(node)`; Starred section visible only when non-empty; alias nodes with canonical `kind`/`data` and shorthand `displayName`, NOT in `nodesByRef`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_sidebar.py`:

```python
def testStarBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    # No Starred section while nothing is starred
    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")

    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    assert [child.data for child in starRoot.children] == ["refs/heads/master"]
    assert starRoot.children[0].kind == SidebarItem.LocalBranch

    # Canonical node lookup unaffected: findNodeByRef resolves OUTSIDE Starred
    canonical = rw.sidebar.findNodeByRef("refs/heads/master")
    assert canonical.parent.kind != SidebarItem.StarredHeader

    # The alias carries a fully functional branch menu; unstar via the alias
    alias = starRoot.children[0]
    menu = rw.sidebar.makeNodeMenu(alias)
    assert findMenuAction(menu, r"switch to")
    triggerMenuAction(menu, r"^unstar branch")
    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)


def testStarRemoteBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")

    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    alias = starRoot.children[0]
    assert alias.kind == SidebarItem.RemoteBranch
    assert alias.data == "refs/remotes/origin/master"
    assert alias.displayName == "origin/master"


def testStarredBranchPersistsAcrossReopen(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")

    mainWindow.closeTab(0)
    rw = mainWindow.openRepo(wd)
    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    assert [child.data for child in starRoot.children] == ["refs/heads/master"]


def testStarredBranchPrunedWhenBranchDeleted(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git branch doomed", wd)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/doomed")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^star branch")
    assert rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)

    node = rw.sidebar.findNodeByRef("refs/heads/doomed")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"^delete")
    acceptQMessageBox(rw, r"delete branch")

    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)
    assert "refs/heads/doomed" not in rw.sidebar.sidebarModel.repoModel.prefs.starredRefs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -x -q -k Star`
Expected: FAIL at `SidebarItem.StarredHeader` (no such member) or the missing menu entry.

- [ ] **Step 3: Prefs field + model changes**

`repoprefs.py`:

```python
    starredRefs: set = field(default_factory=set)
```

`sidebarmodel.py`:

1. Enum — append after `RefFolder` (collapse hashes key on `.name`, so position is free):

```python
    StarredHeader = enum.auto()
```

2. `SidebarLayout.RootItems` — insert before `LocalBranchesHeader`:

```python
        SidebarItem.StarredHeader,
        SidebarItem.Spacer,
```

3. Layout/behavior sets (`sidebarmodel.py:72-101`): inspect each set; add `StarredHeader` wherever `LocalBranchesHeader` appears EXCEPT sets tied to branch sorting or hide/show patterns. List each set touched (or deliberately not) in the task report.

4. In `rebuild()`: make the root loop skip the section when empty, and populate aliases AFTER all `populateRefNodeTree` calls (so `nodesByRef` is complete for kind lookup):

```python
        rootItems = list(SidebarLayout.RootItems)
        if not repoModel.prefs.starredRefs:
            starredAt = rootItems.index(SidebarItem.StarredHeader)
            del rootItems[starredAt:starredAt + 2]   # header + its spacer
        rootNode = SidebarNode(SidebarItem.Root)
        for eitem in rootItems:
            rootNode.appendChild(SidebarNode(eitem))
```

```python
        # --- Starred section (fork) ---------------------------------------
        # Aliases only: never registered in nodesByRef, so the canonical node
        # keeps winning findNodeByRef/indexForRef (jump, highlight, tests).
        starred = repoModel.prefs.starredRefs
        if starred:
            starredRoot = rootNode.findChild(SidebarItem.StarredHeader)
            stale = {ref for ref in starred if ref not in self.nodesByRef}
            if stale:
                starred -= stale
                repoModel.prefs.setDirty()
            for refName in sorted(starred):
                canonical = self.nodesByRef[refName]
                alias = SidebarNode(canonical.kind, refName)
                alias.displayName = RefPrefix.split(refName)[1]
                starredRoot.appendChild(alias)
```

Note the edge: if pruning empties `starred`, the (already-created) header shows once with no children for this rebuild and disappears on the next; acceptable. If the display of the header title needs a label (check how other headers get their text — likely keyed off the enum in a captions map), add "Starred" there with `_("Starred")`.

- [ ] **Step 4: Sidebar toggle + menu entries**

`sidebar.py` — add the toggle method near `wantHideNode`, mirroring its refresh tail exactly (read `wantHideNode` first; reuse whatever signal/refresh call it makes after mutating prefs):

```python
    def wantToggleStarNode(self, node: SidebarNode):
        prefs = self.sidebarModel.repoModel.prefs
        refName = node.data
        if refName in prefs.starredRefs:
            prefs.starredRefs.discard(refName)
        else:
            prefs.starredRefs.add(refName)
        prefs.setDirty()
        # ...same refresh mechanism as wantHideNode's tail...
```

Menu entries — in BOTH the local-branch and remote-branch blocks, directly before the `&Hide in Graph` action:

```python
                ActionDef(_("Unsta&r Branch") if isStarred else _("Sta&r Branch"),
                          lambda: self.wantToggleStarNode(node)),
```

with, near the top of each block:

```python
        isStarred = data in model.repoModel.prefs.starredRefs
```

(`data` is the full refname in both blocks. Verify `&r` is unique per block; local block uses Re`&n`ame not `&R`.)

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -x -q -k Star`
Expected: all PASS. Known trap: if `testStarBranch`'s unstar step can't find the menu entry, the regex `^star branch` may be matching "Unstar Branch" — the `^` anchors prevent this; keep them.

- [ ] **Step 6: Full sidebar suite + duplicate-node audit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -q`
Expected: all PASS. Additionally grep app code (not tests) for `findNodesByKind` and `.walk()` consumers over branch kinds; confirm none misbehaves with alias duplicates (report findings; fix if one does).

- [ ] **Step 7: Commit**

```bash
git add gitfourchette/repoprefs.py gitfourchette/sidebar/sidebarmodel.py gitfourchette/sidebar/sidebar.py test/test_sidebar.py
git commit -m "feat: starred branches pinned under a Starred sidebar section

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Full-suite verification

**Files:** none expected.

- [ ] **Step 1: Full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 0 failed. Baseline before this plan: 967 passed / 16 skipped on `fork-main` (if `feat/multiselect-rebase` has been merged in the meantime, the baseline is higher — either way, 0 failed is the bar; triage any failure as pre-existing vs introduced).

- [ ] **Step 2: Manual smoke (deferred to user)**

Note for the session log: check the Starred section look, the collapse defaults on a real multi-remote repo, quiet fetch feel, and the rename checkbox. Do not block on it.

- [ ] **Step 3: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix: full-suite fallout from UX quick wins batch

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
