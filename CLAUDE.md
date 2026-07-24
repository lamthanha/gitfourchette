# Forkette (GitFourchette fork)

Personal fork of [jorio/gitfourchette](https://github.com/jorio/gitfourchette) (GPL-3) serving as a Fork.dev replacement on Linux (Fedora KDE).
Roadmap: Phase 1 rebase foundation (DONE) → Phase 2 interactive rebase → Phase 3 worktree management → UX polish.

## Key documents

- Design spec (all phases): `docs/superpowers/specs/2026-07-24-gitfourchette-fork-design.md`
- Phase 1 plan (the pattern to follow for new plans): `docs/superpowers/plans/2026-07-24-rebase-foundation.md`
- Execution ledger + deferred-findings backlog: `.superpowers/sdd/progress.md` (git-ignored, read it before planning new work)

## Hard rules

- `master` mirrors upstream exactly; ALL work happens on `fork-main`. Remotes: `origin` = lamthanha's fork, `upstream` = jorio.
- Mutations run the real git binary via `RepoTask.flowCallGit(...)` — NEVER reimplement rebase/merge/worktree logic in pygit2 (pygit2 is for reads only). This matches upstream's own architecture.
- New code goes in new modules where possible (see `gitfourchette/tasks/rebasetasks.py`) to keep upstream merges conflict-free. Register new tasks in BOTH `gitfourchette/tasks/__init__.py` and `TaskBook.names` in `taskbook.py` (dicts are alphabetized). No `TaskBook.icons` entries (no icon assets for these).
- Every `git rebase` invocation passes `GIT_EDITOR=true` (use the `GIT_NO_EDITOR` dict, copied with `dict(...)`).
- UI strings: always `_("...")` localization, typographic `…` and `’`. Check that a new menu entry's `&X` mnemonic is unique within its menu.
- pygit2's `Branch.is_checked_out()` is **worktree-wide** — never use it to mean "is the current branch". The user works in linked worktrees daily; features must stay usable when a branch is checked out in another worktree.
- Rebase confirm dialog appears ONLY when the worktree is dirty (Fork-style); clean trees rebase immediately.

## Testing

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto` (full suite ~40-70s; must be 0 failed before committing).
- `.venv` uses `--system-site-packages` with Fedora's `python3-pyqt6` (system Qt → KDE/Breeze integration).
- Test patterns: `test/test_tasks_rebase.py` (drive real context menus/dialogs, assert commit parentage and `repo.state()`); helpers in `test/util.py`, canned repos via `unpackRepo`, scenarios via `runShellScript(script, wd)`.
- TDD is the norm: failing test first, then implementation.

## Conventions

- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- App identity: display name "Forkette", but `APP_SYSTEM_NAME`/`APP_IDENTIFIER`/package name stay `gitfourchette` (settings location + merge cleanliness). Version carries `+fork`.
