# Test-suite failure triage — 2026-07-25

A file-by-file pytest sweep on 2026-07-25 (fork-main @ 05e595d5, clean tree) reported
many failures. This document triages each report: real fork regression, latent upstream
bug, or environment/transient.

**Environment for this triage:** Python 3.14.6, PySide6 6.11.1 (selected by pytest-qt —
see “Qt binding selection” below), PyQt6 6.11.0 also installed, pygit2 1.19.3 /
libgit2 1.9.4, pytest 9.1.1, Fedora 44, Wayland session available.
All reruns were done on clean fork-main @ 05e595d5 in an isolated worktree, single
pytest process per file, both with the default platform (wayland) and with
`QT_QPA_PLATFORM=offscreen`.

**Bottom line:** with the one-line fix in §1, a full single-process suite run
(offscreen, PySide6, `-X faulthandler`) is completely green:
**1009 passed, 16 skipped, exit 0, in 9 m 52 s** — no segfault, no teardown crash.

## Verdict summary

| Report | Verdict | Detail |
|---|---|---|
| test_regexes.py: 14 failed | **Real bug — fixed** | Latent *upstream* bug exposed by Python 3.14. See §1. |
| test_sidebar.py: 2 × TimeoutError | Not reproducible | §2 |
| test_tasks_commit.py: KeyError + hang | Not reproducible | §3 |
| test_filelist.py: 32 failed | Not reproducible (flaky-prone waits) | §4 |
| test_gpgsigning (12), test_graphview (9), test_gitfourchette (8), test_mainwindow (2), test_lfs (2) | Not reproducible | §4 |
| Segfaults: test_diff, test_mount, test_remotelink | Not reproducible; test_mount/test_remotelink don’t even run without opt-in flags | §5 |
| CommitPathspecFilter `__del__` RuntimeError at teardown | Upstream latent teardown fragility, not a fork change | §6 |

No evidence was found that any of the reported failures is a **fork** regression:
the only deterministic bug found (§1) exists identically on upstream `origin/master`.

## 1. test_regexes.py — missing `import urllib.parse` (FIXED)

`gitfourchette/webhost.py` did `import urllib` but used `urllib.parse.quote` in
`WebHost.makeLink`. Importing the `urllib` package does **not** import the `parse`
submodule; it only worked when a third-party import chain happened to import
`urllib.parse` first. On Python 3.14 in this venv, `import pytest` no longer pulls in
`urllib.parse` (verified: `'urllib.parse' in sys.modules` is False after
`import pytest` + `import gitfourchette.webhost`), so all 14 WebHost tests failed with
`AttributeError: module 'urllib' has no attribute 'parse'`.

- The same line exists on upstream `origin/master` → upstream latent bug, not a fork
  regression. Worth reporting upstream.
- Fixed by importing `urllib.parse` explicitly (one line). All 48 tests pass.
- Side note: `WebHost.makeLink` is called when building sidebar context menus
  (sidebar.py). An exception there aborts menu construction, which would surface as
  `summonContextMenu` TimeoutErrors in unrelated-looking tests — but A/B runs with the
  buggy webhost.py did **not** reproduce the sidebar/gpgsigning/graphview failures, so
  those were not caused by this bug.

## 2. test_sidebar.py TimeoutErrors — not reproducible

`testSidebarCollapseExpandAllFolders` and `testSidebarFilterCollapseState` reportedly
failed with `TimeoutError: retry failed after 5000 ms` even in isolation. Attempted
reproductions, all green:

- 5 × isolation runs (wayland), full-file run (57 passed), 3 × isolation offscreen,
  isolation with the §1 bug re-introduced, isolation under full-core CPU load.

The timeout in question is `summonContextMenu`’s `waitUntilTrue(getVisibleContextMenu)`
— i.e. the QMenu never became visible within 5 s in the sweep’s session. Most plausible
causes: compositor/session state or machine load at sweep time (another agent session
was active on this machine on 2026-07-25).

## 3. test_tasks_commit.py — not reproducible

`testCheckoutCommitDetachHead` (both params) passes in isolation; the full file
(36 tests) passes in ~33 s with no hang.

## 4. Bulk failure counts — cleared on rerun

With the §1 fix, under offscreen: test_gpgsigning 14/14, test_graphview 34/34,
test_gitfourchette 46/46, test_mainwindow 6/6, test_lfs 12 passed + 6 skipped,
test_sidebar 57/57, test_tasks_commit 36/36 — all green.
A/B with the buggy webhost.py: test_gpgsigning and test_graphview still fully green,
so their sweep failures weren’t caused by §1 either.

test_filelist.py: first rerun had 6 failures (TimeoutErrors on QFileDialog waits +
search-highlight assertions); an immediate identical rerun and later runs were 58/58
green. The failures the sweep saw (32) and my transient 6 are load/timing sensitive,
not deterministic.

## 5. “Segfault” files — not reproducible; two of them don’t even run

- test_diff.py: 57 passed, offscreen, PySide6, exit 0.
- test_mount.py: **all 3 tests skip** unless `TESTFUSE=1` (`test.py --with-fuse`).
- test_remotelink.py: **all 6 tests skip** unless `TESTNET=1` (`test.py --with-network`).

If the sweep saw segfaults in test_mount/test_remotelink, the crash must have happened
in interpreter/Qt teardown after skipping everything, or the sweep ran through
`test.py`, which auto-enables pytest-xdist (`-n auto`) — worker crashes under xdist can
present as hard crashes. Not reproducible single-process here.

## 6. `RepoModel.__del__` → CommitPathspecFilter RuntimeError

`RepoModel.__del__` (repomodel.py) calls `self.commitPathspecFilter.deleteLater()`.
The sweep saw shiboken raise `RuntimeError: Internal C++ object (CommitPathspecFilter)
already deleted` during the mainWindow fixture teardown (conftest.py `waitUntilTrue`),
adjacent to a segfault.

- This code is identical on upstream `origin/master` (introduced by upstream commit
  5fdf242b) — **not a fork change**.
- The RepoModel/filter object graph is cyclic (filter → CommitFileSearch → GraphView →
  RepoWidget → RepoModel), so destruction order at GC/teardown time is not guaranteed;
  touching another QObject wrapper from `__del__` is inherently fragile under
  PySide6 + cyclic GC. pytest 9’s unraisable-exception handling can also attribute such
  `__del__` errors to unrelated tests.
- Did not reproduce in any run here, including the full single-process suite run
  (1009 passed, 16 skipped, faulthandler enabled, no crash).
- If it recurs, the low-risk hardening is
  `with suppress(RuntimeError): self.commitPathspecFilter.deleteLater()` — skipping
  deleteLater on an already-deleted C++ object is always safe. Not applied, to keep the
  fork’s upstream delta minimal for an unreproduced crash.

## Qt binding selection — a triage footgun

With both PyQt6 and PySide6 installed:

- `python -c "from gitfourchette import qt"` → **PyQt6** (app default order).
- `python -m pytest …` → **PySide6**, because `test/__init__.py` defers to pytest-qt’s
  preference (PySide6 first) when neither `QT_API` nor `PYTEST_QT_API` is set.
- `./test.py` → **PyQt6** by default (`--qt pyqt6` default), and adds xdist `-n auto`.

So “plain pytest” and “test.py” sweeps exercise *different Qt bindings and process
models*. When comparing results, pin the binding explicitly (e.g.
`PYTEST_QT_API=pyside6`) and note whether xdist was active.

## How to re-run this triage

```bash
# from a worktree at fork-main, with .venv -> main checkout's venv
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/ -q          # PySide6, serial
QT_QPA_PLATFORM=offscreen PYTEST_QT_API=pyqt6 .venv/bin/python -m pytest test/ -q
```
