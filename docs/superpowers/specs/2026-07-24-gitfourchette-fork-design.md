# GitFourchette Fork: Rebase & Worktree Support — Design

- **Date:** 2026-07-24
- **Status:** Approved by user (design); spec pending user review
- **Upstream:** `jorio/gitfourchette` v1.9.1 (forked at commit `bc5d438d`)

## Goal

A full daily-driver Git client on Linux (Fedora KDE) replacing Fork (fork.dev), built by forking GitFourchette and adding the features the user misses most from Fork, in priority order:

1. **"Rebase onto here"** — rebase the current branch onto an arbitrary commit from the graph.
2. **Interactive rebase** — reorder, drop, squash, fixup, reword commits.
3. **Worktree support** — list, add, remove, prune, and open worktrees.
4. UI & feel refinements — explicitly secondary; the user will adapt to GitFourchette's existing UI.

Everything else a daily driver needs (staging with hunk/line control, commit, fetch/pull/push, stash, diff viewer, branch management) GitFourchette already provides.

## Background: how GitFourchette works (v1.9.1)

- Python ≥ 3.10, Qt via PyQt6/PySide6, pygit2 ≥ 1.14.1.
- **Reads** (history, refs, status, diffs) use pygit2/libgit2 through the `Repo` subclass in `gitfourchette/porcelain.py`.
- **Mutations and network ops** run the real `git` binary via `GitDriver` (a `QProcess` wrapper, `gitfourchette/gitdriver/gitdriver.py`), invoked from `RepoTask` coroutines with `flowCallGit(...)` (`gitfourchette/tasks/repotask.py`). Upstream is actively migrating more operations to the CLI. **All new features follow this CLI-first pattern; no pygit2 rebase reimplementation.**
- Every operation is a `RepoTask`: a `flow()` generator that can show dialogs (`flowDialog`, `flowConfirm`), run git (`flowCallGit`, with `autoFail=False` to tolerate conflict exits), declare prereqs, set refresh effects (`TaskEffects`), and is registered in `tasks/__init__.py` + `taskbook.py`, then wired into menus with `TaskBook.action(...)`.
- **Rebase support today: none.** Any `RepositoryState.REBASE*` renders a read-only "unsupported state" banner in `RepoWidget.refreshBanner` (`repowidget.py`).
- **Worktrees today: open-only.** Worktree-aware gitdir plumbing exists (`Repo.commondir`, `Repo.in_gitdir`) and is tested; there is no management UI.
- Conflict resolution UI (`ConflictView` + `tasks/indextasks.py` resolution tasks) is operation-agnostic and will be reused unchanged for rebase conflicts.
- Cherry-pick (`tasks/committasks.py: CherrypickCommit`) is the reference implementation for a conflict-tolerant CLI-driven task.

## Licensing

GitFourchette is GPL-3; the fork remains GPL-3. Private/work use is unrestricted (GPL obligations trigger only on distribution). The fork is not relicensable or sellable as proprietary software; a hypothetical future commercial product would be a from-scratch rewrite (separate project, out of scope).

## Repo strategy

- GitHub fork: `lamthanha/gitfourchette`. Remotes: `origin` = fork, `upstream` = jorio.
- Branches: `master` stays a clean mirror of upstream. Default working branch **`fork-main`**; feature branches merge into it; upstream releases merge in via `master`.
- **New-file policy:** new code lives in new modules to keep upstream merges nearly conflict-free:
  - `gitfourchette/tasks/rebasetasks.py`
  - `gitfourchette/tasks/worktreetasks.py`
  - `gitfourchette/forms/rebasetododialog.py`
  - Unavoidable touches to existing files are kept small: registrations in `tasks/__init__.py` and `taskbook.py`, menu entries in `graphview.py` / `sidebar.py`, banner handling in `repowidget.py`, sidebar model additions.
- App identity stays GitFourchette; version gets a `+fork` suffix in `appconsts.py`.

## Phase 1 — Rebase foundation

Goal: the app becomes rebase-capable, including rebases started outside the app.

### `RebaseOnto` task (`tasks/rebasetasks.py`)

- **Entry points:** graph context menu on a single commit — "Rebase HEAD onto here"; sidebar local-branch menu — "Rebase current branch onto ⟨branch⟩".
- **Confirm dialog:** current branch name, target (short hash or ref name), count of commits that will be replayed (from merge-base), and an **autostash** checkbox (default checked, not persisted in v1). *Amended 2026-07-24 (user request after real-world use): the dialog appears only when the worktree is dirty — clean trees rebase immediately, matching Fork.*
- **Execution:** `flowCallGit("rebase", target, [--autostash])` with `autoFail=False` and `GIT_EDITOR=true` in the environment.
  - Exit 0 → effects `Refs|Head|Workdir`, status message "Rebased ⟨branch⟩ onto ⟨target⟩".
  - Exit ≠ 0 with `repo.state()` in `REBASE*` → conflict pause; refresh; the rebase banner takes over.
  - Exit ≠ 0 otherwise → error dialog with git's stderr (`GitDriver.htmlErrorText()`).
- **Prereqs:** `NoConflicts`. Detached HEAD is allowed (git supports it; the banner falls back to a short hash when no branch name is available).

### Rebase state banner (`repowidget.py: refreshBanner`)

- Handle `RepositoryState.REBASE`, `REBASE_MERGE`, `REBASE_INTERACTIVE` (currently "unsupported").
- Progress read from the gitdir: `rebase-merge/msgnum`, `end`, `head-name`, `onto` (fallback: `rebase-apply/next`, `last`).
- Banner text: "Rebasing ⟨branch⟩: step *i* of *n*", plus a conflict hint while `repo.any_conflicts`.
- Buttons: **Continue / Skip / Abort** → tasks `ContinueRebase`, `SkipRebase`, `AbortRebase` wrapping `git rebase --continue/--skip/--abort` (`GIT_EDITOR=true` on continue).
- Continue is blocked with an explanatory message while `repo.any_conflicts` is true (resolve first via the existing `ConflictView`).

### Phase 1 tests

Clean rebase onto ancestor/descendant; conflicting rebase → banner → resolve in ConflictView → Continue → verify history; Skip; Abort restores pre-rebase state; a rebase started via CLI in the test repo shows a functional banner when the app opens it.

## Phase 2 — Interactive rebase

### Entry point

Graph context menu on a commit: **"Interactive rebase from here…"** — the todo covers commits from the selected commit (inclusive) up to HEAD; base = selected commit's parent. If the range contains merge commits, the confirm step warns that git's default flattening applies.

### `RebaseTodoDialog` (`forms/rebasetododialog.py`)

- Table of the commits in the range, **newest at top** (matching the graph view); rows converted to git's oldest-first todo order on write. A hint explains execution order.
- Per row: action combo (**pick / drop / squash / fixup / reword**), short hash, summary, author. Drag-and-drop reordering; multi-select to set an action on several rows at once.
- Reword rows expose an inline message editor; a squash row exposes the combined message (pre-filled with the concatenated messages, editable).
- Live validation: the first-executed commit cannot be squash/fixup (nothing to fold into); OK disabled if every row is dropped.

### `InteractiveRebase` task execution (`tasks/rebasetasks.py`)

- Runs `git rebase -i <base>` via `flowCallGit` with two helper scripts in the environment:
  - `GIT_SEQUENCE_EDITOR` → helper that overwrites git's todo file with the dialog's prepared list.
  - `GIT_EDITOR` → helper that pops pre-collected messages (numbered files in a temp dir) for reword/squash prompts; when the queue is empty it leaves the file untouched (accepts git's default), so unexpected editor invocations degrade gracefully.
- Helpers are generated as small temp scripts by the task; payloads live in a per-invocation temp dir.
- Conflicts mid-sequence pause into the Phase 1 banner (Continue/Skip/Abort). `ORIG_HEAD` and the reflog remain the safety net; no custom undo in v1.
- Success → effects `Refs|Head|Workdir`, jump to HEAD.

### Phase 2 tests

Reorder two commits; drop; squash with edited message; fixup; reword; conflict mid-sequence then resolve + continue; abort restores the original ref. Tests drive the actual dialog rows programmatically (pytest-qt), then assert on resulting history.

## Phase 3 — Worktrees

### Sidebar section

- New **"Worktrees"** section alongside branches/remotes/stashes/submodules.
- Data source: parse `git worktree list --porcelain` (via `GitDriver.runSync`) during repo model refresh → per entry: directory name, path, branch or detached hash, locked/prunable flags.
- The main worktree is listed and labeled "(main)"; the currently open worktree is highlighted. Listing works whether the open repo is the main or a linked worktree.

### Tasks (`tasks/worktreetasks.py`)

- **`NewWorktree`** — dialog: path (default sibling `../<reponame>-<branch>`), and branch mode: check out an existing branch, or create a new branch from a chosen ref. Runs `git worktree add [-b <new>] <path> <ref>`; on success, offers to open the new worktree as a tab.
- **`RemoveWorktree`** — confirm; if git refuses because the tree is dirty, offer a force retry (`--force`). Blocked with a message if the target is the main worktree or is currently open in a tab.
- **`PruneWorktrees`** — `git worktree prune`.
- **`OpenWorktree`** — opens via the existing `MainWindow.openRepo` (double-click on a sidebar entry does the same).
- Branch context menu addition: **"Checkout in new worktree…"** (pre-fills `NewWorktree` with that branch) — the Fork workflow.

### Phase 3 tests

Add (existing branch and new branch); list contents; remove; force-remove dirty; prune; open as tab; checkout-branch-in-new-worktree. Existing helpers (`makeBareCopy`, CLI-created worktrees in `test/util.py`) are reused.

## Error handling

All new tasks ride the existing machinery: `AbortTask` for controlled bails, git stderr surfaced via `GitDriver.htmlErrorText()`, conflict flow through `ConflictView`, UI refresh through `TaskEffects`. No new error frameworks.

## Non-goals (v1)

- No pygit2-based rebase implementation.
- No merge-conflict-resolver or cherry-pick enhancements.
- No UI/feel restyling (revisit after the three phases land).
- No `edit`/`exec`/`break` todo actions in interactive rebase (add later if wanted).
- No commercial/from-scratch rewrite.

## Risks & notes

- Upstream migrates libgit2→CLI actively; merges may occasionally conflict in the few shared touch-points (`taskbook.py`, `graphview.py`, `repowidget.py`) — mitigated by the new-file policy.
- Git version requirements are ancient (worktree porcelain list ≥ 2.7, autostash ≥ 2.9); Fedora's git is far newer. Minimum stays whatever upstream requires (≥ 2.41 for some fetch features).
- PyQt6's GPL license is a non-issue since the fork stays GPL-3.

## Success criteria

Entirely within the GUI, the user can: rebase the current branch onto an arbitrary commit including conflict resolution; reorder/drop/squash/fixup/reword commits via interactive rebase; create, open, remove, and prune worktrees; and continue or abort a rebase that was started in a terminal.
