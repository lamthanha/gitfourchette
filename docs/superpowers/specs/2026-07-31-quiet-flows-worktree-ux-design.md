# Quiet Flows & Worktree UX Batch — Design

- **Date:** 2026-07-31
- **Status:** Approved by user (design); spec pending user review
- **Baseline:** `fork-main` (`a4d1a5c5`), suite 1082 passed / 16 skipped.
- **Slot in roadmap:** UX-polish phase (after Phase 3 + follow-ups + sidebar/staging batch).

## Goal

Ten small Fork-parity improvements from the user's 2026-07-31 idea list plus the
ledger's open list: quiet switch/open flows, worktree creation from remote
branches, a worktree path template, worktree move, New Worktree dialog fixes,
same-repo tab adjacency, plain tab titles, and an honest "Commit and Push"
button caption.

## Triage record (what's NOT in this batch and why)

- **Apply a single file from a stash — already exists upstream.** Verified
  empirically: select the stash in the graph, right-click a file →
  *Restore File Revision… → As Of This Commit* restores only that file's
  stashed content. This batch adds a pin test so the behavior never regresses
  silently (see Testing), but no product code.
- **Multi-branch "Filter" (hide all but N)** — moved to the future list by
  user. Note for that future design: `RepoPrefs.showPatterns` is already a
  set; upstream's `toggleHideRefPattern(allButThis=True)` deliberately clears
  it to hold one entry (`repomodel.py:504`). The work is toggle semantics +
  menu UX, not storage.
- **Inline commit box (Fork-style, docked under staging area)** — future list
  by user ("quick fix now, inline box later"). The modal dialog already has a
  separate summary line-edit + description box; what's missing vs Fork is the
  dockedness, a much larger feature.
- **Edge-style visual tab groups** — rejected (deep `QTabBar2` surgery, poor
  interplay with tab-color dots and `[M]` markers, low marginal value).
  Replaced by feature C8 (adjacency).
- **Worktree-aware friendly error messages** (fetch code-128 into held branch;
  fast-forward refusal showing "divergent branches") — user chose to leave on
  the backlog.

## Features

### A1. Quiet branch switch

Menu "Switch to X" and double-click switch **immediately, with no confirmation
dialog** — except when the repo has submodules, where today's dialog stays
because its "Update submodules recursively" checkbox does real work
(`branchtasks.py:61-72`).

Unchanged safety boundaries:

- The **held-in-another-worktree** path (`branchtasks.py:39-60`): still shows
  the "Open that worktree?" offer.
- The **detached-HEAD warning** (`branchtasks.py:76-87`): still shown; it
  fires independently of the confirmation branch.
- **Git's own refusals** (dirty file would be clobbered, etc.): `flowCallGit`
  surfaces git's error text in the normal task-error dialog. We do NOT
  pre-check the workdir — git already implements the safety check, and a
  clean switch is the common case.

Mechanics: the `askForConfirmation=True` branch of `SwitchBranch.flow` shows
the dialog only when `self.repo.listall_submodules_fast()` is non-empty.
`askForConfirmation=False` callers (NewBranch's switch-to checkbox,
CheckoutCommit) are unaffected.

Test impact: upstream tests that pin the "Do you want to switch…" box run on
canned repos without submodules — they go quiet and need justified
adaptation (accept/reject-box lines removed; assertions on the switch result
kept verbatim). A submodule-repo test pins that the dialog+checkbox path
survives.

### A2. Quiet open of a newly created worktree

`NewWorktree` stops asking "Open it in a new tab?" after `git worktree add`
succeeds — the new worktree's tab opens directly (`rw.openRepo.emit`), same
as accepting today's offer. `flowConfirmOpenNewWorktree`
(`worktreetasks.py:42`) is deleted.

Test impact: the three tests that drive the offer box
(`testNewWorktreeExistingBranch`, `testNewWorktreeNewBranchAndOpenTab`,
`testCheckoutBranchInNewWorktreeFromBranchMenu`) drop their
accept/rejectQMessageBox lines; tab-count assertions flip to "opens
directly". A new assertion pins that creation + open happens with **zero**
message boxes.

### B3. New worktree from a remote branch

The remote-branch context menu gains **"New Worktree Here…"**, prefilling
`NewWorktreeDialog`:

- No same-shorthand local branch exists → **create-new-branch mode**: name =
  branch tail (`origin/foo` → `foo`), base = the remote ref.
  `git worktree add -b foo <path> origin/foo` sets up tracking automatically
  (git's default when branching from a remote-tracking ref).
- A same-shorthand local **exists but is not checked out anywhere** →
  **existing-branch mode** prefilled with that local (avoids a guaranteed
  "branch already exists" failure).
- Local is **checked out in some worktree** → unchanged precedence: the menu
  keeps showing "Open in <wt> Worktree" (Phase 3 Amendment), no new entry.

Dialog change: the "from:" base-ref combo gains remote branches, listed after
locals. Mnemonic uniqueness in the remote-branch menu checked at plan time.

### B4. Worktree path template preference

Global preference (default reproduces today's behavior) controlling the
dialog's default path. Variables use the vocabulary of VS Code's
Git-worktree-manager extension per user request:

| Variable | Meaning |
| --- | --- |
| `$BASE_PATH` | main worktree root (e.g. `/home/u/ws/beans-api`) |
| `$BASE_ROOT` | parent directory of the repo root |
| `$REPO_NAME` | basename of the repo root |
| `$BRANCH` | branch name, `/` sanitized to `-` |

- Default: `$BASE_ROOT/$REPO_NAME-$BRANCH` (== current
  `defaultPathForBranch`).
- User's target layout expressible as `$BASE_PATH-worktrees/$BRANCH`.
- Unknown `$VARS` are left literal; a template yielding an empty path falls
  back to the default. Live path tracking in the dialog
  (`_trackDefaultPath`) renders the template.
- Stored in global `Prefs` next to the other fork prefs; shown in Settings
  (exact category slot chosen at plan time, precedent: `tabColorBindings`).

### B5. Move worktree

New `MoveWorktree(RepoTask)` on the worktree leaf menu ("Mo&ve Worktree…" —
mnemonic checked against the leaf menu at plan time): a small path dialog
prefilled with the current path → `git worktree move <old> <new>` →
`TaskEffects.Refs`.

Guards, mirroring `RemoveWorktree`:

- Main worktree → blocked with a message (git refuses anyway; we say why).
- Open in a tab → blocked ("Close its tab before moving it."). Auto-reopen
  after move is deferred.
- Locked worktree → git's own refusal text surfaces via the task-error
  dialog.

### B6. New Worktree dialog width (ledger open-list item)

`self.resize(max(640, self.width()), self.height())` after layout setup —
the `newtagdialog.py:74` idiom, so long translated labels can still widen
it. 640 fits a ~55-char path.

### B7. New Worktree dialog radio auto-select (ledger open-list item)

Typing in the new-branch name field must flip the mode — today the typed
name is **silently discarded** if the "existing branch" radio is still
checked (`_revalidate` passes, OK enabled, task takes the existing-branch
path).

- `newNameEdit.textEdited` (user typing only — NOT `textChanged`, so the
  `setNewBranch()` test API and programmatic `setText` stay inert) checks
  `newRadio`.
- `existingCombo.activated` (user pick only — NOT `currentTextChanged`,
  which fires during `addItems`) checks `existingRadio`.
- Regression test: type a name without touching the radios → accept → the
  new branch is actually created.

### C8. Same-repo tab adjacency

A newly opened tab whose repo shares a **common gitdir** with an existing
tab inserts **after the last such sibling** instead of at the far end, so
same-repo worktree tabs cluster; tab colors carry the rest of the signal.

- One hook in `MainWindow._openRepo`'s default-placement path; an explicit
  `tabIndex` (e.g. `openRepoNextTo`) still wins.
- Sibling detection is path-based (`tabcolors.repoBindingKey` precedent) so
  it works for stub (unloaded) tabs too.
- Session restore keeps its saved order — no reordering of existing tabs,
  ever; only the insertion point of new tabs changes.

### C9. Plain tab titles (drop parent-path disambiguation)

Tabs always show the plain basename (or the user's nickname). The
duplicate-title disambiguation pass in `MainWindow.refreshAllTabTexts` and
the `disambiguateTabTitlesByPath` helper (`toolbox/pathutils.py:30` — fork
code) are **deleted**, along with their tests. Rationale: parent paths are
long, and per-repo tab colors + `[M]` markers already distinguish repos
(user decision).

### D10. "Commit and Push" button caption

When the commit dialog is invoked via `CommitAndPush` (Shift+Commit), its OK
button and window title read **"Commit and Push"** instead of "Commit", so
the button says what will actually happen.

- `NewCommit.flow` gains an optional caption override parameter (minimal
  upstream-file edit in `committasks.py`; default `None` preserves upstream
  behavior everywhere else).
- `CommitAndPush.flow` passes `_("Commit and Push")` through
  `flowSubtask(NewCommit, ...)`.
- Amend path untouched.

## Sequencing

All features sit on `fork-main` (`a4d1a5c5`); no cross-feature file overlap
worth sequencing except:

- **A2 and B3/B7 both edit `worktreetasks.py`/`newworktreedialog.py` tests** —
  same plan task or adjacent tasks to avoid churn.
- **C8 and C9 both touch `mainwindow.py` tab code** — one task.

Single spec → single plan (~8 tasks incl. integration), executed
subagent-driven in a throwaway sibling worktree per house convention.

## House rules honored

- New task (`MoveWorktree`) in the existing fork module
  `tasks/worktreetasks.py`; dual registration (`tasks/__init__.py`,
  `TaskBook.names`, alphabetized); no `TaskBook.icons` entries.
- All mutations (`checkout`, `worktree add/move`, `push`) via `flowCallGit`;
  pygit2 read-only.
- UI strings `_()`-localized, typographic `…`/`’`; mnemonic uniqueness
  checked per menu.
- No `Branch.is_checked_out()` misuse; every feature stays correct with
  linked worktrees (B3 precedence rule, B5 guards).
- Upstream-file edits kept minimal: `branchtasks.py` (A1 condition),
  `committasks.py` (D10 param), `mainwindow.py` (C8 hook, C9 deletion).

## Testing

TDD per house norm — failing test first, per feature:

1. **A1**: submodule-free repo switches with zero message boxes (menu +
   double-click); submodule repo still shows dialog + checkbox; held-elsewhere
   offer and detached-HEAD warning still fire; dirty-clobber refusal surfaces
   git's error. Adapted upstream tests keep their post-switch assertions.
2. **A2**: create worktree → tab opens with zero message boxes; decline-path
   tests adapted.
3. **B3**: remote branch → dialog prefilled new-branch mode with tracking
   verified via `git branch -vv`; same-shorthand-local variant prefills
   existing-branch mode; held-elsewhere shows no new entry.
4. **B4**: template renders all four variables; empty/garbage template falls
   back; dialog tracks template live.
5. **B5**: move relocates the worktree (old path gone, new path listed);
   main-worktree and open-in-tab blocked; sidebar refreshes.
6. **B6**: dialog width ≥ 640 on open.
7. **B7**: type-name-without-radio → branch created (the silent-discard
   repro); combo pick flips back.
8. **C8**: opening a sibling worktree inserts adjacent to its cluster;
   unrelated repo still appends at end; explicit `openRepoNextTo` unaffected.
9. **C9**: two same-basename repos both show the bare basename; nickname
   still wins; disambiguation tests deleted.
10. **D10**: Shift-commit path shows "Commit and Push" button/title; plain
    commit dialog unchanged.
11. **Ride-along pin**: restore-single-file-from-stash (the verified existing
    behavior) gets a permanent regression test.

Full suite 0 failed on top of the 1082-passed baseline; ruff green on all
changed files.

## Success criteria

Entirely in the GUI: switching branches in a submodule-free repo is
instant and silent (unsafe switches still refused by git with a clear
error); creating a worktree lands you directly in its new tab; a remote
branch can be turned into a new worktree (tracking set up) from its context
menu; the default worktree path follows a user-set template with
`$BASE_PATH`/`$BASE_ROOT`/`$REPO_NAME`/`$BRANCH`; a worktree can be moved
from the sidebar; the New Worktree dialog opens wide enough to read the
path and never silently discards a typed branch name; same-repo tabs
cluster together; tab titles are plain basenames; and Shift+Commit's dialog
button honestly reads "Commit and Push".
