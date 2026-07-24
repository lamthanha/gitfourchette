# Rebase Foundation (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GitFourchette fork rebase-capable: "Rebase onto here" from the commit graph and sidebar, plus a rebase-state banner with Continue/Skip/Abort — including rebases started outside the app.

**Architecture:** New `RepoTask` subclasses in a new module `gitfourchette/tasks/rebasetasks.py` drive the real `git rebase` binary through the app's existing `flowCallGit` machinery (never pygit2 rebase). `RepoWidget.refreshBanner` learns the three `RepositoryState.REBASE*` states. Conflicts reuse the existing ConflictView flow untouched.

**Tech Stack:** Python ≥3.10, PyQt6, pygit2 (reads only), pytest + pytest-qt.

## Global Constraints

- Repo: `/home/admin/workspace.personal/gitfourchette`, branch `fork-main`. Spec: `docs/superpowers/specs/2026-07-24-gitfourchette-fork-design.md`.
- All commands run from the repo root. Test runner: `.venv/bin/python -m pytest` (Task 1 creates `.venv`).
- Every user-facing string goes through `_("...")` from `gitfourchette.localization` (star-imported). Match the codebase's typographic characters in UI strings: `…` for ellipsis, `’` for apostrophe.
- New files start with the repo's standard 5-line header comment (GPL v3 notice, see any existing file).
- New task classes MUST be registered in `gitfourchette/tasks/__init__.py` AND `TaskBook.names` (else `autoActionName` warns at runtime). No `TaskBook.icons` entries (no rebase icon asset exists).
- Rebase states constant used throughout: `REBASE_STATES = (RepositoryState.REBASE, RepositoryState.REBASE_INTERACTIVE, RepositoryState.REBASE_MERGE)`.
- Never call git with an interactive editor: pass `env={"GIT_EDITOR": "true"}` on every `rebase` invocation.
- Commit after each task with the trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Dev environment + test baseline

**Files:**
- Create: `.venv/` (untracked)
- Possibly modify: `.gitignore` (only if `.venv` isn't ignored)

**Interfaces:**
- Consumes: nothing.
- Produces: working `.venv/bin/python -m pytest` for all later tasks.

- [ ] **Step 1: Create venv and install with test extras**

```bash
cd /home/admin/workspace.personal/gitfourchette
python3 -m venv .venv
.venv/bin/pip install -e ".[test,pyqt6]"
```

Expected: install succeeds (pygit2 wheel, PyQt6, pytest, pytest-qt).

- [ ] **Step 2: Verify the existing suite passes (subset for speed)**

Run: `.venv/bin/python -m pytest test/test_tasks_branch.py -x -q`
Expected: all tests PASS (this file exercises merge/reset/switch — our closest neighbors). If Qt complains about a missing display, prefix with `QT_QPA_PLATFORM=offscreen ` (and use that prefix for every pytest run in this plan).

- [ ] **Step 3: Ensure `.venv` is ignored**

Run: `git status --short`
Expected: no `.venv` entry. If it appears, append a `.venv/` line to `.gitignore` and commit:

```bash
git add .gitignore
git commit -m "chore: ignore .venv

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `RebaseOnto` task + graph context menu

**Files:**
- Create: `gitfourchette/tasks/rebasetasks.py`
- Modify: `gitfourchette/tasks/__init__.py` (new import block after the `branchtasks` block, line ~27)
- Modify: `gitfourchette/tasks/taskbook.py` (`names` dict ~line 92, `tips` dict ~line 143)
- Modify: `gitfourchette/graphview/graphview.py` (import + `_contextMenuActions1Commit`, after the `ResetHead` action at line ~473)
- Create: `test/test_tasks_rebase.py`

**Interfaces:**
- Consumes: `RepoTask`, `AbortTask`, `TaskPrereqs`, `TaskEffects` from `gitfourchette.tasks.repotask`; `flowCallGit(*args, env=..., autoFail=False) -> GitDriver`; `argsIf` from `gitfourchette.gitdriver`; `NavLocator` from `gitfourchette.nav`.
- Produces: `class RebaseOnto(RepoTask)` with `flow(self, onto: Oid | str)` (str must be a full refname like `refs/heads/master`); module constant `REBASE_STATES: tuple[RepositoryState, ...]`; test helper `makeDivergentBranches(tempDir) -> str` in `test/test_tasks_rebase.py`. Task 3 and Task 4 rely on these exact names.

- [ ] **Step 1: Write the failing test**

Create `test/test_tasks_rebase.py`:

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import re

from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from .util import *


def makeDivergentBranches(tempDir) -> str:
    """Unpack a canned repo, then create branch 'feature' diverging from
    'master': both add a commit touching clash.txt with different content.
    Leaves 'feature' checked out. Returns the workdir path."""
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c feature master
        echo "feature version" > clash.txt
        git add clash.txt
        git commit -m "feature: clash"
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        git switch master
        echo "master version" > clash.txt
        git add clash.txt
        git commit -m "master: clash"
        git switch feature
        """,
        wd)
    return wd


def testRebaseOntoClean(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript(
        """
        git switch -c feature master
        echo "feature only" > feature.txt
        git add feature.txt
        git commit -m "feature: own file"
        git switch master
        echo "master only" > master.txt
        git add master.txt
        git commit -m "master: own file"
        git switch feature
        """,
        wd)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target
    oldFeatureTip = rw.repo.branches.local["feature"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"rebase.+feature.+onto")

    assert rw.repo.state() == RepositoryState.NONE
    newTip = rw.repo.branches.local["feature"].target
    assert newTip != oldFeatureTip
    newTipCommit = rw.repo.peel_commit(newTip)
    assert newTipCommit.message.startswith("feature: own file")
    assert newTipCommit.parents[0].id == masterTip


def testRebaseOntoNothingToDo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    headId = rw.repo.head_commit_id

    rw.jump(NavLocator.inCommit(headId))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"nothing to rebase")
    assert rw.repo.state() == RepositoryState.NONE


def testRebaseOntoConflict(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target

    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"rebase.+feature.+onto")

    assert rw.repo.state() in (
        RepositoryState.REBASE,
        RepositoryState.REBASE_INTERACTIVE,
        RepositoryState.REBASE_MERGE)
    assert rw.repo.any_conflicts
```

(Import style verified against `test/test_tasks_branch.py`: `from .util import *` is correct, and `NavLocator.inUnstaged` exists.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py -x -q`
Expected: FAIL — `triggerContextMenuAction` raises because no menu item matches `rebase.+onto here`.

- [ ] **Step 3: Create `gitfourchette/tasks/rebasetasks.py`**

```python
# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging

from gitfourchette.gitdriver import GitDriver, argsIf
from gitfourchette.localization import *
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects, TaskPrereqs
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

REBASE_STATES = (
    RepositoryState.REBASE,
    RepositoryState.REBASE_INTERACTIVE,
    RepositoryState.REBASE_MERGE,
)

GIT_NO_EDITOR = {"GIT_EDITOR": "true"}


class RebaseOnto(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, onto: Oid | str):
        repo = self.repo

        if repo.state() != RepositoryState.NONE:
            raise AbortTask(_("Conclude the ongoing operation before rebasing."))

        # Resolve target (sidebar passes a refname, graph passes an Oid)
        if isinstance(onto, str):
            assert onto.startswith("refs/")
            reference = repo.references[onto]
            ontoId = reference.target
            ontoDisplay = reference.shorthand
            assert isinstance(ontoId, Oid)
        else:
            ontoId = onto
            ontoDisplay = shortHash(onto)

        if repo.head_is_detached:
            branchName = shortHash(repo.head_commit_id)
        else:
            branchName = repo.head_branch_shorthand

        headId = repo.head_commit_id
        ahead, _behind = repo.ahead_behind(headId, ontoId)
        if ahead == 0:
            raise AbortTask(
                _("There’s nothing to rebase: {0} has no commits of its own "
                  "beyond {1}.", bquo(branchName), bquo(ontoDisplay)),
                icon="information")

        autostashCheckbox = QCheckBox(_("Autostash (stash uncommitted changes, then reapply them)"))
        autostashCheckbox.setChecked(True)
        text = paragraphs(
            _("Do you want to rebase {0} onto {1}?", bquo(branchName), bquo(ontoDisplay)),
            _n("{n} commit will be replayed.", "{n} commits will be replayed.", n=ahead))
        yield from self.flowConfirm(text=text, verb=_("Rebase"), checkbox=autostashCheckbox)
        autostash = autostashCheckbox.isChecked()

        self.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
        driver = yield from self.flowCallGit(
            "rebase",
            *argsIf(autostash, "--autostash"),
            str(ontoId),
            env=dict(GIT_NO_EDITOR),
            autoFail=False)

        yield from self.flowEnterWorkerThread()
        repo.refresh_index()
        stillRebasing = repo.state() in REBASE_STATES
        yield from self.flowEnterUiThread()

        _concludeRebaseCommand(
            self, driver, stillRebasing,
            _("Rebased {0} onto {1}.", tquo(branchName), tquo(ontoDisplay)))


def _concludeRebaseCommand(task: RepoTask, driver: GitDriver, stillRebasing: bool, successStatus: str):
    """Shared epilog for every git-rebase invocation: a nonzero exit is only an
    error if the repo did NOT end up in (or remain in) a rebase state."""
    if driver.exitCode() != 0 and not stillRebasing:
        raise AbortTask(driver.htmlErrorText())
    if stillRebasing:
        task.epilog.status = _("Rebase interrupted: resolve conflicts, then continue the rebase.")
        task.epilog.jumpTo = NavLocator.inWorkdir()
    else:
        task.epilog.status = successStatus
```

- [ ] **Step 4: Register the task**

In `gitfourchette/tasks/__init__.py`, after the `branchtasks` import block (ends line 27), add:

```python
from gitfourchette.tasks.rebasetasks import (
    RebaseOnto,
)
```

In `gitfourchette/tasks/taskbook.py`:
- `names` dict, next to `tasks.ResetHead` (line ~92): `tasks.RebaseOnto: _("Rebase onto"),`
- `tips` dict, next to `tasks.ResetHead` (line ~143): `tasks.RebaseOnto: _("Replay this branch’s commits on top of another commit"),`

- [ ] **Step 5: Add the graph context menu entry**

In `gitfourchette/graphview/graphview.py`:
- Add `RebaseOnto` to the module's task imports (find the line importing `ResetHead` near the top and extend it).
- In `_contextMenuActions1Commit`, directly after the `ResetHead` action (line ~473), insert:

```python
            TaskBook.action(self, RebaseOnto, _("Re&base {0} onto Here…", myRef), taskArgs=oid),
```

- [ ] **Step 6: Run the new tests**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py -x -q`
Expected: 3 PASS. (`testRebaseOntoConflict` leaves the repo mid-rebase with the generic "unsupported state" banner — that's expected until Task 3.)

- [ ] **Step 7: Run neighboring suites to catch regressions**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py test/test_tasks_branch.py -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tasks/rebasetasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/graphview/graphview.py test/test_tasks_rebase.py
git commit -m "feat: add Rebase Onto task to commit graph context menu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Rebase banner with Continue / Skip / Abort

**Files:**
- Modify: `gitfourchette/tasks/rebasetasks.py` (add `rebaseProgress`, `ContinueRebase`, `SkipRebase`, `AbortRebase`)
- Modify: `gitfourchette/tasks/__init__.py`, `gitfourchette/tasks/taskbook.py` (register the three tasks)
- Modify: `gitfourchette/repowidget.py` (`refreshBanner`, lines ~593–666)
- Test: `test/test_tasks_rebase.py`

**Interfaces:**
- Consumes: `REBASE_STATES`, `GIT_NO_EDITOR`, `_concludeRebaseCommand`, `makeDivergentBranches` from Task 2.
- Produces: `ContinueRebase`, `SkipRebase`, `AbortRebase` (all `flow(self)`, no args); `rebaseProgress(repo: Repo) -> tuple[int, int, str]` returning (step, total, branchShorthand) with zeros/empty when unknown. `refreshBanner` gains a `bannerButtons: list[tuple[str, Callable]]` mechanism.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_tasks_rebase.py`:

```python
def _bannerButton(rw, pattern: str):
    return next(b for b in rw.mergeBanner.buttons
                if re.search(pattern, b.text(), re.I) and b.isVisibleTo(rw))


def _startConflictedRebase(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target
    rw.jump(NavLocator.inCommit(masterTip))
    triggerContextMenuAction(rw.graphView.viewport(), r"rebase.+onto here")
    acceptQMessageBox(rw, r"rebase.+feature.+onto")
    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.mergeBanner.isVisibleTo(rw)
    assert re.search(r"rebasing", rw.mergeBanner.label.text(), re.I)
    return rw


REBASE_STATES_FOR_TESTS = (
    RepositoryState.REBASE,
    RepositoryState.REBASE_INTERACTIVE,
    RepositoryState.REBASE_MERGE)


def testRebaseConflictBannerAndAbort(tempDir, mainWindow):
    rw = _startConflictedRebase(tempDir, mainWindow)
    oldFeatureTip = rw.repo.branches.local["feature"].target

    _bannerButton(rw, r"abort").click()
    acceptQMessageBox(rw, r"abort.+rebase")

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.mergeBanner.isVisibleTo(rw)
    assert rw.repo.branches.local["feature"].target == oldFeatureTip


def testRebaseConflictResolveAndContinue(tempDir, mainWindow):
    rw = _startConflictedRebase(tempDir, mainWindow)
    masterTip = rw.repo.branches.local["master"].target

    # Resolve the conflict by taking THEIRS (the feature branch's version)
    rw.jump(NavLocator.inUnstaged("clash.txt"))
    assert rw.conflictView.isVisibleTo(rw)
    rw.conflictView.ui.theirsButton.click()
    acceptQMessageBox(rw, r".")

    _bannerButton(rw, r"continue").click()

    assert rw.repo.state() == RepositoryState.NONE
    newTip = rw.repo.peel_commit(rw.repo.branches.local["feature"].target)
    assert newTip.message.startswith("feature: own file")
    # Rebased chain sits on top of master's tip
    assert newTip.parents[0].parents[0].id == masterTip


def testRebaseSkipCommit(tempDir, mainWindow):
    rw = _startConflictedRebase(tempDir, mainWindow)
    masterTip = rw.repo.branches.local["master"].target

    _bannerButton(rw, r"skip").click()
    acceptQMessageBox(rw, r"skip")

    assert rw.repo.state() == RepositoryState.NONE
    newTip = rw.repo.peel_commit(rw.repo.branches.local["feature"].target)
    # The conflicting commit was skipped; only "feature: own file" remains
    assert newTip.message.startswith("feature: own file")
    assert newTip.parents[0].id == masterTip


def testRebaseStartedOutsideApp(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    runShellScript("git rebase master || true", wd)
    rw = mainWindow.openRepo(wd)

    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
    assert rw.mergeBanner.isVisibleTo(rw)
    assert re.search(r"rebasing", rw.mergeBanner.label.text(), re.I)
    for pattern in (r"continue", r"skip", r"abort"):
        assert _bannerButton(rw, pattern) is not None
```

Adjust the conflict-resolution step to the real ConflictView API if `theirsButton` doesn't exist under that name — copy whatever `test/test_tasks_commit.py::testCherrypickWithConflicts` does (it drives `rw.conflictView.ui.theirsButton`); if a confirmation box text differs, loosen the `acceptQMessageBox` pattern accordingly.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py -x -q`
Expected: first new test FAILs — banner shows the generic "unsupported state" warning, `_bannerButton` raises `StopIteration`.

- [ ] **Step 3: Add progress helper + three tasks to `rebasetasks.py`**

```python
def rebaseProgress(repo: Repo) -> tuple[int, int, str]:
    """Return (step, total, branchShorthand) for the rebase in progress.
    Zeros/empty string when unknown."""
    from pathlib import Path
    from contextlib import suppress

    for stateDir, stepFile, endFile in (
            ("rebase-merge", "msgnum", "end"),
            ("rebase-apply", "next", "last")):
        base = Path(repo.in_gitdir(stateDir, common=False))
        if not base.is_dir():
            continue

        def read(name: str) -> str:
            with suppress(OSError):
                return (base / name).read_text("utf-8").strip()
            return ""

        with suppress(ValueError):
            step = int(read(stepFile) or 0)
            total = int(read(endFile) or 0)
            headName = read("head-name")
            branch = RefPrefix.split(headName)[1] if headName else ""
            return step, total, branch
    return 0, 0, ""


class _RebaseSequencerTask(RepoTask):
    """Base class for continue/skip/abort."""

    def checkRebasing(self):
        if self.repo.state() not in REBASE_STATES:
            raise AbortTask(_("No rebase is in progress."), icon="information")


class ContinueRebase(_RebaseSequencerTask):
    def flow(self):
        self.checkRebasing()
        self.repo.refresh_index()
        if self.repo.any_conflicts:
            raise AbortTask(_("Fix merge conflicts before continuing the rebase."))

        self.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
        driver = yield from self.flowCallGit(
            "rebase", "--continue", env=dict(GIT_NO_EDITOR), autoFail=False)

        yield from self.flowEnterWorkerThread()
        self.repo.refresh_index()
        stillRebasing = self.repo.state() in REBASE_STATES
        yield from self.flowEnterUiThread()
        _concludeRebaseCommand(self, driver, stillRebasing, _("Rebase completed."))


class SkipRebase(_RebaseSequencerTask):
    def flow(self):
        self.checkRebasing()
        yield from self.flowConfirm(
            text=_("Do you want to skip the current commit and continue the rebase?"),
            verb=_("Skip"))

        self.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
        driver = yield from self.flowCallGit(
            "rebase", "--skip", env=dict(GIT_NO_EDITOR), autoFail=False)

        yield from self.flowEnterWorkerThread()
        self.repo.refresh_index()
        stillRebasing = self.repo.state() in REBASE_STATES
        yield from self.flowEnterUiThread()
        _concludeRebaseCommand(self, driver, stillRebasing, _("Rebase completed."))


class AbortRebase(_RebaseSequencerTask):
    def flow(self):
        self.checkRebasing()
        yield from self.flowConfirm(
            text=_("Do you want to abort the rebase and return the branch to its previous state?"),
            verb=_("Abort rebase"),
            icon="warning")

        self.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
        yield from self.flowCallGit("rebase", "--abort", env=dict(GIT_NO_EDITOR))
        self.epilog.status = _("Rebase aborted.")
```

- [ ] **Step 4: Register the three tasks**

`tasks/__init__.py` — extend the rebasetasks import block:

```python
from gitfourchette.tasks.rebasetasks import (
    AbortRebase,
    ContinueRebase,
    RebaseOnto,
    SkipRebase,
)
```

`taskbook.py` `names` dict:

```python
            tasks.AbortRebase: _("Abort rebase"),
            tasks.ContinueRebase: _("Continue rebase"),
            tasks.SkipRebase: _("Skip commit and continue rebase"),
```

- [ ] **Step 5: Teach `refreshBanner` the rebase states**

In `gitfourchette/repowidget.py`, inside `refreshBanner` (line ~593):

1. After `bannerCallback = None` (line ~603), add: `bannerButtons = []`.
2. Before the final `else:` fallback branch (line ~653), insert:

```python
        elif rstate in (RepositoryState.REBASE, RepositoryState.REBASE_INTERACTIVE, RepositoryState.REBASE_MERGE):
            from gitfourchette.tasks.rebasetasks import rebaseProgress
            step, total, rebasingBranch = rebaseProgress(repo)
            bannerTitle = _("Rebasing {0}", bquo(rebasingBranch)) if rebasingBranch else _("Rebasing")
            if step and total:
                bannerTitle += f" ({step}/{total})"

            if not repo.any_conflicts:
                bannerText += _("Continue the rebase to proceed.")
                bannerHeeded = True
            else:
                bannerText += _("Conflicts need fixing.")

            # Insertion order is reversed by Banner.addButton; add Abort first
            # so the visual order is Continue, Skip, Abort.
            bannerButtons = [
                (englishTitleCase(_("Abort rebase")), lambda: tasks.AbortRebase.invoke(self)),
                (englishTitleCase(_("Skip")), lambda: tasks.SkipRebase.invoke(self)),
                (englishTitleCase(_("Continue")), lambda: tasks.ContinueRebase.invoke(self)),
            ]
```

3. In the closing block (line ~660), after the existing `addButton(bannerAction, bannerCallback)` call, add:

```python
                for buttonText, buttonCallback in bannerButtons:
                    self.mergeBanner.addButton(buttonText, buttonCallback)
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py -x -q`
Expected: all PASS. If `testRebaseSkipCommit` fails because `git rebase --skip` stops again (both commits conflict), fix the *scenario*, not the code: only the "feature: clash" commit touches `clash.txt`, so skip must proceed cleanly through "feature: own file".

- [ ] **Step 7: Regression run**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py test/test_tasks_branch.py test/test_tasks_conflict.py -q`
Expected: all PASS (refreshBanner changes must not break merge/cherry-pick/revert banners).

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tasks/rebasetasks.py gitfourchette/tasks/__init__.py gitfourchette/tasks/taskbook.py gitfourchette/repowidget.py test/test_tasks_rebase.py
git commit -m "feat: rebase state banner with continue/skip/abort

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Sidebar "Rebase onto branch" entry

**Files:**
- Modify: `gitfourchette/sidebar/sidebar.py` (local-branch menu, after the `MergeBranch` entry at lines ~236–241; plus the module's task import)
- Test: `test/test_tasks_rebase.py`

**Interfaces:**
- Consumes: `RebaseOnto.flow(onto: Oid | str)` — the str branch of the signature (full refname), from Task 2; test helpers `makeDivergentBranches(tempDir)` (Task 2) and `REBASE_STATES_FOR_TESTS` (Task 3) from `test/test_tasks_rebase.py`.
- Produces: menu entry "Rebase ⟨active⟩ onto ⟨branch⟩…" on local branches.

- [ ] **Step 1: Write the failing test**

Append to `test/test_tasks_rebase.py`:

```python
def testRebaseOntoFromSidebar(tempDir, mainWindow):
    wd = makeDivergentBranches(tempDir)
    rw = mainWindow.openRepo(wd)
    masterTip = rw.repo.branches.local["master"].target

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"rebase.+feature.+onto")
    acceptQMessageBox(rw, r"rebase.+feature.+onto.+master")

    # Divergent scenario conflicts, so we should now be mid-rebase
    assert rw.repo.state() in REBASE_STATES_FOR_TESTS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py::testRebaseOntoFromSidebar -x -q`
Expected: FAIL — no matching menu item.

- [ ] **Step 3: Add the sidebar entry**

In `gitfourchette/sidebar/sidebar.py`: add `RebaseOnto` to the task imports at the top of the file (same import statement that brings in `MergeBranch`). Then in the local-branch menu, directly after the `MergeBranch` action (lines ~236–241), insert:

```python
                TaskBook.action(
                    self,
                    RebaseOnto,
                    _("Re&base {0} onto {1}…", activeBranchDisplay, thisBranchDisplay),
                    taskArgs=refName,
                ).replace(enabled=not isCurrentBranch and bool(activeBranchName)),
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest test/test_tasks_rebase.py -x -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/sidebar/sidebar.py test/test_tasks_rebase.py
git commit -m "feat: rebase-onto entry in sidebar branch menu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Fork version suffix + full-suite verification

**Files:**
- Modify: `gitfourchette/appconsts.py` (line ~15, `APP_VERSION`)

**Interfaces:**
- Consumes: nothing new.
- Produces: version string `"1.9.1+fork"` (pyproject reads it dynamically — verify install still works).

- [ ] **Step 1: Bump version string**

In `gitfourchette/appconsts.py` change `APP_VERSION = "1.9.1"` to `APP_VERSION = "1.9.1+fork"`. If a companion constant like `APP_VERSION_SUFFIX` exists nearby, leave it untouched.

- [ ] **Step 2: Verify packaging still parses the version**

Run: `.venv/bin/pip install -e . --no-deps -q && .venv/bin/python -c "import gitfourchette.appconsts as a; print(a.APP_VERSION)"`
Expected: prints `1.9.1+fork` with no install error (PEP 440 local version — valid).

- [ ] **Step 3: Full test suite**

Run: `.venv/bin/python -m pytest test -q`
Expected: everything PASSes (pre-existing failures, if any, must also exist on `master` — verify with `git stash && .venv/bin/python -m pytest <failing test> -q && git stash pop` before blaming our changes).

- [ ] **Step 4: Launch the app for a manual smoke test**

Run: `.venv/bin/python -m gitfourchette` — open a real repo, right-click a commit, confirm "Rebase ⟨branch⟩ onto Here…" appears and the confirm dialog shows the commit count. Close without rebasing anything important.

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/appconsts.py
git commit -m "chore: mark fork version 1.9.1+fork

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
