# UX Quick Wins + Starred Branches — Design

- **Date:** 2026-07-25
- **Status:** Approved by user (design); spec pending user review
- **Baseline:** `fork-main` after Phase 2 + multi-select addendum plan (`86a3f448`)
- **Slot in roadmap:** before Phase 3 (worktrees)

## Goal

Five small Fork-parity UX improvements, batched: copy branch name, quiet fetch,
sensible sidebar collapse defaults, rename-remote-branch checkbox, and starred
branches. Triage of the user's original 11-item list is recorded below so the
findings aren't lost.

## Triage record (2026-07-25)

**Already in GitFourchette 1.9.1 — no work, discoverability only:**

| Wish | Existing feature |
| --- | --- |
| Filter local branches | Sidebar search: `Ctrl+F` / `/` (`sidebar/sidebarfilter.py`) |
| Double-click stages/unstages | Pref `doubleClickFileList` (+ `middleClickFileList`), `settings.py:170` |
| Clone dialog clipboard/focus | `clonedialog.py:46` clipboard URL guess; `:89` URL field focus |
| Search commits by path | `Alt+P` "Find path touched by commits" (`graphview/commitfilesearch.py`) |

**Deferred by decision (not in this batch):**

- *Repo title merged into toolbar row* — cosmetic; layout surgery in upstream
  `mainwindow.py` with recurring merge friction. Revisit in the UX-polish phase.
- *Changes as trees* — file lists are flat `QListView`s; a tree mode is a
  model rework across dirty/staged/committed views. Own phase if still wanted.
- *Pickaxe (`git log -S`) content search* — `Alt+P` path search likely covers
  the need; revisit on demand.

## Features

### 1. Copy branch name

Context-menu entry **"Copy Branch &Name"** on sidebar local-branch and
remote-branch nodes. Copies the shorthand (`feature/x`, `origin/feature/x`)
to the clipboard. Follows the existing "Copy Remote URL" pattern
(`sidebar.py:409`), including its status-bar confirmation toast.
Not added for tags or stashes.

### 2. Quiet fetch

Manual **Fetch** stops showing the modal `ProcessDialog`; the status-bar busy
spinner (already emitted by the task runner) is the progress indicator.
Mechanism: `FetchRemotes.broadcastProcesses()` and
`FetchRemoteBranch.broadcastProcesses()` return `False` — identical to what
`AutoFetchRemotes` (`nettasks.py:195-197`) already does. Errors keep surfacing
through the normal task-error dialog. **Pull and Push keep the dialog**
(abortable, worth watching). No new preference.

### 3. Sidebar collapse defaults

On opening a repo whose sidebar state was never primed: collapse the **Tags**
section and every **remote subtree except the tracked remote** — the remote of
the current branch's upstream; fallback `origin`; else the first remote. The
Remotes *root* stays expanded (remote names visible). Priming writes the
existing `collapseCache` (`repoprefs.py:35`, persisted in
`.git/gitfourchette.json`) exactly once, guarded by a new boolean RepoPrefs
field (e.g. `sidebarCollapsePrimed`), so a user who expands everything is
never re-collapsed. All subsequent expand/collapse behavior and persistence
is the existing machinery, unchanged.

### 4. Rename remote branch with local rename

The rename-local-branch flow gains a checkbox, shown only when the branch has
an upstream on a remote: **"Also rename ⟨remote/old⟩ on the remote"**,
**default unchecked** (renaming must not become a surprise network push).
When checked: after the local rename succeeds, chain the existing
`RenameRemoteBranch` machinery (`nettasks.py:95-162`: push refspec rename +
upstream retarget) with the new name. If the remote rename fails, the local
rename stands and the error is reported (no rollback). UI: the current rename
dialog is `TextInputDialog` (line-edit only) — it gets an optional-checkbox
extension or a small fork-owned subclass; behavior above is the contract.

### 5. Starred branches

- **Toggle:** context-menu entry **"Star Branch" / "Unstar Branch"** on local
  and remote branch nodes.
- **Storage:** `starredRefs: set[str]` (full refnames) in RepoPrefs —
  per-repo, survives restarts, never synced.
- **Display:** new **"Starred"** section at the top of the sidebar listing
  starred branches as fully functional alias nodes: same context menu, same
  double-click behavior as the original node. Unstarring — or deletion of the
  underlying ref — removes the entry (stale refnames are pruned on model
  rebuild, not persisted forever).
- **Known risk:** the sidebar model is upstream code and its ref→node lookup
  assumes one node per ref; alias nodes must not break jump/highlight
  (`findNodeByRef`). The implementation plan must resolve this (e.g. lookup
  prefers the canonical node). **Approved fallback** if alias nodes prove
  intractable: star icon + sort-to-top within the existing Branches section,
  no new group — but the Starred group is the target.

## Error handling

All features ride existing machinery: tasks (`RepoTask` flows, `AbortTask`,
`TaskEffects`), RepoPrefs persistence, sidebar model refresh. No new error
frameworks. Quiet fetch must not swallow errors: failed fetch still raises
the task-error dialog.

## Testing

House style (pytest-qt, real repos via `unpackRepo`/`runShellScript`, driving
real menus):

1. Copy name: trigger menu on local + remote branch; assert clipboard text.
2. Quiet fetch: fetch with a bare-copy remote; assert no `ProcessDialog`
   child appears and refs updated; error case still shows a message box.
3. Collapse defaults: fresh open → Tags + non-tracked remote subtrees
   collapsed, tracked remote expanded; expand-all + reopen → nothing
   re-collapses (primed flag); existing persistence tests unaffected.
4. Rename w/ remote: checkbox absent without upstream; checked path renames
   both (assert local ref + remote-tracking ref + upstream retarget, using
   the existing `RenameRemoteBranch` test scenario as the template);
   unchecked path leaves remote untouched.
5. Starred: star → node appears under Starred; unstar → disappears; starred
   node context menu still works (e.g. switch); branch deletion prunes the
   entry; restart-persistence via reopening the repo.

## Non-goals

- No title-row/toolbar merge, no tree-view file lists, no pickaxe search
  (see triage record).
- No global (cross-repo) starred list; no starring of tags/stashes.
- No preference UI for collapse defaults or quiet fetch.

## Success criteria

Entirely in the GUI: branch names copyable from the sidebar; fetch runs with
only a status-bar indicator; a freshly opened repo shows collapsed tags and
non-tracked remotes; renaming a tracked branch can rename its remote branch
in the same flow; starring a branch pins a live alias under a Starred group
that survives app restarts.

## Amendment (2026-07-25 evening, user request): tree-structured Starred section

The Starred section shows flat rows with full slashed shorthands (e.g. "feat/multiselect-rebase").
Restructure it to mirror the Local Branches/Remotes presentation: RefFolder hierarchy
("feat" folder containing "multiselect-rebase"), built from the starred refs only.
Constraints: starred rows remain ALIAS nodes (SidebarNode.walk's StarredHeader skip must keep
covering the whole starred subtree so nodesByRef/selection-restore never resolve to an alias);
folder collapse-state must stay INDEPENDENT of the same-named folder in the main sections
(collapse hashes are kind+data — starred folders need distinct data, e.g. a "starred:" prefix,
without breaking their display name); unstarring the last child of a folder removes the folder.
