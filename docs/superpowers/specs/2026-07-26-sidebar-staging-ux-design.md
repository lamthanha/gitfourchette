# Sidebar & Staging UX Batch — Design

- **Date:** 2026-07-26
- **Status:** Approved by user (design); spec pending user review
- **Baseline:** `fork-main` (`ff47d3cd`) **plus** `feat/worktree-followup` once it
  merges — features 1, 4, 5 depend on it landing first (see Sequencing).
- **Slot in roadmap:** UX-polish phase, after the Phase 3 worktree follow-up.

## Goal

Five Fork-parity UX improvements, batched like the earlier UX quick-wins spec:
deeper sidebar indentation, Shift-modifier button variants (Stage All /
Unstage All / Commit and Push), file-list filtering, local-first hide-linkage,
and main-worktree markers (sidebar icon + tab-title prefix).

## Features

### 1. Deeper second-level sidebar indentation (+8px)

Second-level rows (branches, remotes, tags, stashes, submodules, worktrees)
currently paint at nearly the same x as their section headers, because
`SidebarLayout.UnindentItems` retreats them a **full** tree level (16px).

- `SidebarDelegate.unindentRect()` (`sidebardelegate.py:51`) retreats by
  `indentation − CHILD_INDENT` per unindent level instead, with a new module
  constant `CHILD_INDENT = 8`.
- Net effect: every unindented row — and its whole subtree (nested ref
  folders) — shifts uniformly 8px right; headers don't move.
- Paint (`sidebardelegate.py:133`) and click-zone mapping (`sidebar.py:123`)
  share `unindentRect`, so hit-testing stays consistent with no extra work.
- Existing tests that pin absolute click x-coordinates are checked and
  minimally adapted (expansion of the sidebar-polish precedent: adapt
  coordinates only, never semantics).

### 2. Shift-modifier button variants (Fork-style)

While **Shift** is held, three staging-area buttons swap label and action;
release (or window deactivation) restores them. **Discard is deliberately
excluded** (user decision — destructive action stays selection-scoped).

| Button | Normal | Shift held |
| --- | --- | --- |
| Stage | Stage (selection) | **Stage All** |
| Unstage | Unstage (selection) | **Unstage All** |
| Commit | Commit | **Commit and Push** |

Mechanism:

- An application-level event filter (owned by `DiffArea`) tracks Shift
  press/release; `WindowDeactivate` resets to the normal state so the buttons
  can't stick in Shift mode after Alt-Tab.
- Labels/enabled-state swap live: All-variants enable when the *list* is
  non-empty (normal variants keep their selection-based enabling).
- Click handlers also test the modifier at click time, so a fast Shift+click
  works even before the label repaints.
- The commit button's dropdown menu (Amend / Stash) is unchanged under
  Shift; only the main click action swaps.
- **Stage All / Unstage All** act on all rows currently **visible** in the
  respective list — an active filter (feature 3) scopes them, matching Fork.
  They reuse the existing stage/unstage task paths, passing the full visible
  file set.
- **Commit and Push** is a new `CommitAndPush` `RepoTask` in a **new fork
  module**, registered in both `tasks/__init__.py` and `TaskBook.names`
  (alphabetized; no `TaskBook.icons` entry). Flow:
  1. `yield from self.flowSubtask(NewCommit)` — cancelling the commit dialog
     aborts the whole task; nothing is pushed.
  2. Resolve the checked-out branch's upstream.
  3. Upstream set → **quiet push** through the real git binary
     (`flowCallGit`), status-bar indicator only, mirroring quiet fetch.
     No upstream → open the existing Push dialog (`PushBranch`) as the
     fallback (user decision: "silent with dialog fallback").
  4. Push failures surface through the normal task-error dialog.

### 3. File-list filtering (Ctrl+F)

The per-list `SearchBar` on **Unstaged, Staged, and Committed** file lists
switches from jump-search to **filter** semantics — consistent with the
sidebar, whose Ctrl+F already filters (user decision).

- Typing narrows the list: debounced (SearchBar's existing 250ms),
  case-insensitive substring match on the file path.
- Filtering happens **inside `FileListModel`**: it keeps the full delta list
  and rebuilds visible rows when the term changes. No proxy model — the
  codebase widely assumes the view's model *is* the `FileListModel`
  (`FileList.flModel` asserts it).
- The match-highlight delegate keeps highlighting the matching substring in
  visible rows.
- **Esc** hides the bar *and* clears the filter; a hidden bar always means
  "no filter". The forward/backward jump buttons stay hidden (already are).
- Semantics stated plainly: the filter changes what you *see* and what the
  All-buttons (feature 2) scope to; **Commit always commits the whole
  index** — standard git semantics, same as Fork.

### 4. Hide-linkage: the pair follows the local branch

Today hiding is strictly per-ref; any cross-effect is a graph-reachability
artifact (hidden tips flood down, stopping at visible ref tips). New rule,
implemented entirely as a post-pass in
`RepoModel.refreshHiddenRefCache()` (`repomodel.py:520`):

- **Hide mode** (`hidePatterns`): a remote-tracking ref is added to
  `hiddenRefs` when it is the upstream of a hidden local branch — **unless**
  some *visible* local branch also tracks it (visibility wins on shared
  upstreams). Concretely: `hiddenRefs |= (upstreams of hidden locals) −
  (upstreams of visible locals)`. Only upstreams whose remote-tracking ref
  actually exists in `repoModel.refs` are added — a gone/unfetched upstream
  (the "missing upstream" indicator case) must never enter `hiddenRefs`,
  which `getHiddenTips()` indexes into `refs` with.
- **Solo mode** (`showPatterns`, "hide all but this"): the upstream of every
  visible local branch is removed from `hiddenRefs` (user decision: pairing
  applies in both modes).
- Hiding a **remote** branch directly affects only that ref, as today.

No UI changes needed:

- The paired remote ref automatically shows the existing **"indirectly
  hidden" eye** (`isImplicitlyHidden` covers refs in `hiddenRefs` without
  their own pattern).
- The graph updates for free — `getHiddenTips()` reads `hiddenRefs`.
- The implicit state is derived, never stored: un-hiding the local restores
  the pair; prefs contain only the user's own toggles.
- Known pre-existing quirk, unchanged: clicking the eye of an implicitly
  hidden ref first toggles it to *explicitly* hidden.

Tests: pair hides and restores together (sidebar eye state + graph
`hiddenCommits`); remote-only hide leaves the local alone; solo on a local
keeps its upstream visible; two locals sharing an upstream — hiding one
keeps the upstream visible.

### 5. Main-worktree markers

- **Sidebar row:** the main worktree's icon becomes Qt's standard **home
  icon** (folder icon today); the "` (main)`" display-name suffix is
  **dropped** (the icon now carries it). Bold keeps its existing meaning —
  "the worktree this tab lives in". Tooltip (path, branch, warnings)
  unchanged.
- **Tab title:** `RepoWidget.getTitle()` prepends **`[M] `** when the loaded
  repo is a **main worktree with ≥1 linked worktree** (user decisions:
  marker only when the distinction exists; `[M]` over `[H]`/`⌂` because
  "main worktree" is git's own term and a lone H reads as HEAD).
  - Applies to nicknames too (`[M] beans`).
  - Stub (not-yet-loaded) tabs stay unmarked until load — same accepted
    class of behavior as tab-color overrides on stubs.
  - The tab **icon** slot remains owned by tab-color dots; the marker is
    text-only.
  - The duplicate-title disambiguation pass in `refreshAllTabTexts()` runs
    on marked titles and is unaffected (marked main vs unmarked linked
    titles already differ).

## Sequencing

- Features **1, 4, 5** touch `sidebarmodel.py`, `sidebar.py`,
  `worktrees.py`, `test_sidebar.py` — the same files `feat/worktree-followup`
  rewrites. They start **after** that branch merges to `fork-main`.
- Features **2, 3** (`diffarea.py`, `filelists/`, new task module) don't
  overlap it and may be implemented first / in parallel.
- The implementation branch fast-forwards onto `fork-main` (this worktree's
  branch is currently 1 commit behind, no divergence).

## House rules honored

- New task code in a new module; dual registration (`tasks/__init__.py`,
  `TaskBook.names`); no icon entries.
- Mutations (push) run the real git binary via `flowCallGit`; pygit2 stays
  read-only.
- All new UI strings `_()`-localized with typographic `…`/`’`.
- No use of `Branch.is_checked_out()`; nothing here assumes single-worktree
  repos.

## Testing

TDD per house norm — failing test first, per feature:

1. Delegate/click-zone coordinate pins for the new indent.
2. Shift swap: QTest key press/release drives the event filter; Shift+click
   paths assert All-scope actions and the commit→quiet-push chain (canned
   remote repo, as in `test_tasks_net`); no-upstream fallback opens the Push
   dialog; commit-dialog cancel pushes nothing.
3. Filter: term narrows rows across all three lists; Esc restores; Stage All
   under active filter stages only visible files.
4. Hide-linkage matrix (see feature 4).
5. Sidebar icon key + suffix drop; tab-title `[M]` appears only for
   main-with-linked-worktrees, survives nicknames, absent on stubs.

## Success criteria

Entirely in the GUI: second-level sidebar rows are visibly indented under
their headers; holding Shift turns Stage/Unstage/Commit into Stage All /
Unstage All / Commit-and-Push (silent push to upstream, dialog fallback);
typing in a file list's Ctrl+F bar narrows it; hiding a local branch hides
its upstream pair (indirect eye, graph updates) while hiding a remote branch
affects only itself; the main worktree shows a home icon (no "(main)" text)
in the sidebar and its tab reads `[M] name` whenever linked worktrees exist.
