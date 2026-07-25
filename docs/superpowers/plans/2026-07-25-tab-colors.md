# Tab Color Dots with Repo Bindings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Colored dot on each repo tab, driven by a global repo binding (main-worktree realpath → color name, inherited by linked worktrees) plus a per-worktree override, managed from the tab context menu and removable in Settings.

**Architecture:** New module `gitfourchette/tabcolors.py` holds the palette, binding-key derivation, resolution logic, dot icons (recolored SVG asset), and the context-submenu builder. `Prefs.tabColorBindings` (global dict) and `RepoPrefs.tabColorOverride` (per-worktree string) persist state. `MainWindow.refreshTabColors()` applies dots; hooks ride `refreshAllTabTexts()`, tab activation, and prefs-apply. A custom PrefsDialog control lists/removes bindings.

**Tech Stack:** PyQt6 (system Qt), pygit2 for reads only (this feature does zero git mutations), pytest offscreen.

**Spec:** `docs/superpowers/specs/2026-07-25-tab-colors-design.md`

## Sanctioned deviations from the spec (decided at plan time — do not "fix" these back)

1. **`repoBindingKey(workdir: str)` and `resolveTabColorName(workdir, repoPrefs)` take a workdir path, not a `Repo`.** One path-based implementation (parsing `.git` gitfile + `commondir` directly) serves loaded `RepoWidget`s AND unloaded `RepoStub` tabs, so background tabs restored at startup show their dots without opening the repo, and bind-time and resolve-time keys can never disagree. Semantics identical to the spec's `Repo.commondir` rule.
2. **`tabDotIcon` uses a new SVG asset (`gitfourchette/assets/icons/tab-dot.svg`) recolored via `stockIcon(name, colorTable)`** instead of hand-painting a QPixmap. Same visual contract (antialiased circle, darker outline, HiDPI); reuses the existing icon cache (which also provides the spec's caching requirement) and the codebase's icon idiom.
3. **`trtables.py` gets ONE new caption line** (`"tabColorBindings": _("Tab colors"),`). The spec's churn list omits trtables.py, but without it the Settings row caption renders as the raw key. Surface this in the final summary.
4. **`Prefs.tabColorBindings` is staged in `_category_hidden` during Tasks 1–2, moved to `_category_tabs` in Task 3.** PrefsDialog raises `NotImplementedError` for dict fields it has no control for; the field must not enter a visible category until its control exists.

## Global Constraints

- Test runner prefix: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` (run from the worktree root). Full suite: `... -m pytest test -q -n auto`; must be **0 failed** on top of baseline (992 passed / 16 skipped at branch point).
- NO edits to `gitfourchette/tasks/__init__.py` or `gitfourchette/tasks/taskbook.py`. Upstream-file churn limited to: `settings.py` (one field), `repoprefs.py` (one field), `mainwindow.py` (submenu + refresh calls), `forms/prefsdialog.py` (control dispatch + one method), `toolbox/qtabwidget2.py` (thin `setTabIcon` wrapper), `trtables.py` (one caption line). Everything else in NEW files.
- Palette: exactly `red, orange, yellow, green, teal, blue, purple, gray` from `gitfourchette/colors.py`. Persisted values are the color **names** (strings). No new QColor constants.
- Override semantics: `""` = Auto (follow binding), `"none"` = explicitly colorless, else a palette color name. Resolution: override → binding → no dot. Unknown/stale values degrade gracefully (treated as absent).
- Binding key = `os.path.realpath` of the main worktree root (bare repo: the repo dir itself).
- UI strings: `_("...")` localization, typographic `…` and `’`. Mnemonics unique within each (sub)menu.
- Urgent-icon precedence: `stockIcon("urgent-tab")` wins while the tab's `QTabWidget2.UrgentPropertyName` property is set; the dot is re-applied on tab activation.
- TDD: failing test first. One commit per task, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Verified codebase facts (do not re-derive)

- `MainWindow.generateTabContextMenu(i)` at `gitfourchette/mainwindow.py:517` builds menu `MWRepoTabContextMenu` ending with a SEPARATOR + "Configure Tabs…" action. `self.tabs` is a `QTabWidget2` (`gitfourchette/toolbox/qtabwidget2.py`); its inner QTabBar is `self.tabs.tabs`.
- `QTabWidget2.onCurrentChanged` (qtabwidget2.py:300) clears the urgent property and icon BEFORE emitting `currentWidgetChanged`, which MainWindow receives as `onTabCurrentWidgetChanged` (mainwindow.py:484, connected at :80). `QTabWidget2.UrgentPropertyName = "QTabBar2_UrgentFlag"` (:201), set to `"true"` in `requestAttention` (:459). `QTabWidget2` has `setTabText`/`setTabTooltip` wrappers (:351–355) but no `setTabIcon` wrapper yet.
- `MainWindow.refreshAllTabTexts()` (mainwindow.py:908) is called from `_openRepo`, `installRepoWidget`, `replaceRepoWidgetWithStub`, `onRepoNameChanged`, and tab close (5 sites) — a tail call there covers every tab add/load/unload/rename.
- `GFApplication._applyPrefs` (application.py:402) applies `PrefsDialog.prefDiff` on accept, type-checks old vs new value types, then calls `self.mainWindow.onApplyPrefs(changedKeys)` (mainwindow.py:1131).
- `PrefsDialog.makeControlWidget(key, value, caption)` (forms/prefsdialog.py:343) raises `NotImplementedError` for unhandled types (dict!). `self.assign(key, value)` stores into the working-copy `prefDiff`; `self.getMostRecentValue(key)` reads diff-then-prefs. Controls get objectName `prefctl_<key>` automatically in `_newRow`. Module-level helper `vBoxWidget(...)` exists. `GFApplication.instance().openPrefsDialog(focusOnKey)` returns the dialog (application.py:612).
- `stockIcon(iconId, colorTable)` (toolbox/iconbank.py:51) loads `assets:icons/<id>.svg`, applies `"old=new old2=new2"` color substitutions via `RecolorSvgIconEngine` (plain string replacement of color keywords, done once at load), and caches by `(iconId, colorTable)` — so `tabDotIcon` returns the identical QIcon object per color, and `QIcon.cacheKey()` is stable across copies (setTabIcon/tabIcon copies share data).
- `settings.prefs` is a module-level singleton (`settings.py:433`); `PrefsFile.write()` skips fields at default value and `load()` skips unknown keys — old files load fine. In `APP_TESTMODE`, prefs write under `qTempDir()/testmode-config`, wiped by `endSession()` after each test — no cross-test leakage.
- `RepoPrefs` (repoprefs.py:21) writes `gitfourchette.json` into the worktree's own gitdir; `RepoWidget` cleanup writes it when dirty (repowidget.py:394). A loaded tab's prefs: `rw.repoModel.prefs`. `RepoStub` has `.workdir` but no repoModel.
- `Repo.commondir` (porcelain.py:748) resolves `<gitdir>/commondir`; linked worktree gitfile format is `gitdir: <path>` (possibly relative to the workdir).
- Tests: fixtures `(tempDir, mainWindow)`; `mainWindow.openRepo(wd)` returns a loaded `RepoWidget` under ForceSerial; `unpackRepo(tempDir)` returns the workdir **with trailing slash**; `runShellScript(script, wd)`; `triggerMenuAction(menu, "sub/leaf")` and `findMenuAction` use case-insensitive `re.search` per path part on accelerator-stripped titles; `findQDialog(mainWindow, "settings")` locates PrefsDialog.
- trtables prefKey captions for the Tabs category live around `gitfourchette/trtables.py:462`.

---

### Task 1: Core model — `tabcolors.py`, dot asset, pref fields

**Files:**
- Create: `gitfourchette/tabcolors.py`
- Create: `gitfourchette/assets/icons/tab-dot.svg`
- Create: `test/test_tabcolors.py`
- Modify: `gitfourchette/settings.py` (one field in `_category_hidden`, after `refSortClearTimestamp` ~line 202)
- Modify: `gitfourchette/repoprefs.py` (one field after `customKeyFile` ~line 42)

**Interfaces produced (Tasks 2–3 rely on these exact names):**
- `tabcolors.TAB_PALETTE: dict[str, QColor]` — ordered `red, orange, yellow, green, teal, blue, purple, gray`
- `tabcolors.OVERRIDE_NONE = "none"`
- `tabcolors.repoBindingKey(workdir: str) -> str`
- `tabcolors.resolveTabColorName(workdir: str, repoPrefs) -> str` (repoPrefs: `RepoPrefs | None`, duck-typed `.tabColorOverride`)
- `tabcolors.tabDotIcon(colorName: str) -> QIcon`
- `settings.prefs.tabColorBindings: dict[str, str]`
- `RepoPrefs.tabColorOverride: str = ""`

- [ ] **Step 1: Write the failing tests** — create `test/test_tabcolors.py`:

```python
# -----------------------------------------------------------------------------
# Forkette extension tests — tab color dots with repo bindings.
# -----------------------------------------------------------------------------

import os
from types import SimpleNamespace

from gitfourchette import tabcolors
from .util import *


def testRepoBindingKeyMainWorktree(tempDir):
    wd = unpackRepo(tempDir)
    assert tabcolors.repoBindingKey(wd) == os.path.realpath(wd)


def testRepoBindingKeyLinkedWorktree(tempDir):
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    assert tabcolors.repoBindingKey(linked) == os.path.realpath(wd)


def testRepoBindingKeySymlinkedPath(tempDir):
    wd = unpackRepo(tempDir)
    link = os.path.join(tempDir.name, "sympath")
    os.symlink(os.path.normpath(wd), link)
    assert tabcolors.repoBindingKey(link) == os.path.realpath(wd)


def testRepoBindingKeyBareRepo(tempDir):
    wd = unpackRepo(tempDir)
    runShellScript("git clone --bare . ../Bare.git", wd)
    bare = os.path.join(os.path.dirname(os.path.normpath(wd)), "Bare.git")
    assert tabcolors.repoBindingKey(bare) == os.path.realpath(bare)


def testResolveTabColorNamePrecedence(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    key = tabcolors.repoBindingKey(wd)

    # No binding, no override
    assert tabcolors.resolveTabColorName(wd, None) == ""

    # Binding alone
    settings.prefs.tabColorBindings[key] = "orange"
    assert tabcolors.resolveTabColorName(wd, None) == "orange"

    # Auto override follows binding
    ns = SimpleNamespace(tabColorOverride="")
    assert tabcolors.resolveTabColorName(wd, ns) == "orange"

    # Explicit "none" override beats binding
    ns.tabColorOverride = "none"
    assert tabcolors.resolveTabColorName(wd, ns) == ""

    # Color override beats binding
    ns.tabColorOverride = "blue"
    assert tabcolors.resolveTabColorName(wd, ns) == "blue"

    # Unknown override value degrades to binding
    ns.tabColorOverride = "bogus"
    assert tabcolors.resolveTabColorName(wd, ns) == "orange"

    # Unknown binding value degrades to no dot
    settings.prefs.tabColorBindings[key] = "bogus"
    assert tabcolors.resolveTabColorName(wd, None) == ""


def testTabDotIconCachedAndDistinct(mainWindow):
    assert tabcolors.tabDotIcon("red") is tabcolors.tabDotIcon("red")
    assert tabcolors.tabDotIcon("red").cacheKey() == tabcolors.tabDotIcon("red").cacheKey()
    assert tabcolors.tabDotIcon("red").cacheKey() != tabcolors.tabDotIcon("blue").cacheKey()
    for name in tabcolors.TAB_PALETTE:
        icon = tabcolors.tabDotIcon(name)
        assert not icon.isNull()
        assert not icon.pixmap(16, 16).isNull()


def testTabColorPrefFieldsDefaultsAndRoundTrip(tempDir, mainWindow):
    from gitfourchette import settings

    # Global bindings dict: default empty, survives write/load
    assert settings.prefs.tabColorBindings == {}
    settings.prefs.tabColorBindings["/some/path"] = "teal"
    settings.prefs.setDirty()
    assert settings.prefs.write(force=True)
    settings.prefs.reset()
    assert settings.prefs.tabColorBindings == {}
    settings.prefs.load()
    assert settings.prefs.tabColorBindings == {"/some/path": "teal"}

    # Per-worktree override: default empty on a real repo
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert rw.repoModel.prefs.tabColorOverride == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'gitfourchette.tabcolors'` (collection error is acceptable as the failing state).

- [ ] **Step 3: Create the SVG asset** — `gitfourchette/assets/icons/tab-dot.svg`:

```svg
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
<circle cx='8' cy='8' r='5.5' fill='red' stroke='black' stroke-width='1'/>
</svg>
```

(The literal keywords `red` and `black` are substitution targets for `stockIcon`'s colorTable; they never render as-is.)

- [ ] **Step 4: Create `gitfourchette/tabcolors.py`:**

```python
# -----------------------------------------------------------------------------
# Forkette extension — not part of upstream GitFourchette.
# Tab color dots: global repo bindings + per-worktree overrides.
# Resolution: override -> repo binding -> no dot.
# -----------------------------------------------------------------------------

import os
from pathlib import Path

from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.toolbox import stockIcon

TAB_PALETTE: dict[str, QColor] = {
    "red": colors.red,
    "orange": colors.orange,
    "yellow": colors.yellow,
    "green": colors.green,
    "teal": colors.teal,
    "blue": colors.blue,
    "purple": colors.purple,
    "gray": colors.gray,
}

OVERRIDE_NONE = "none"
"tabColorOverride value: explicitly colorless despite a repo binding."


def repoBindingKey(workdir: str) -> str:
    """
    Binding key for the repo containing this worktree: realpath of the main
    worktree's root (or of the repo dir itself for a bare repo).

    Parses .git gitfiles and commondir files directly (no pygit2) so it also
    works for unloaded tabs, and bind-time/resolve-time keys always agree.
    """
    workdir = os.path.realpath(workdir)
    gitdir = os.path.join(workdir, ".git")

    if os.path.isfile(gitdir):
        # Linked worktree (or submodule): .git is a file "gitdir: <path>"
        try:
            pointer = Path(gitdir).read_text("utf-8").strip()
        except OSError:
            return workdir
        if not pointer.startswith("gitdir:"):
            return workdir
        pointer = pointer.removeprefix("gitdir:").strip()
        gitdir = os.path.realpath(os.path.join(workdir, pointer))

    commondirFile = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondirFile):
        try:
            relCommon = Path(commondirFile).read_text("utf-8").strip()
        except OSError:
            relCommon = ""
        if relCommon:
            gitdir = os.path.realpath(os.path.join(gitdir, relCommon))

    if os.path.basename(gitdir) == ".git":
        return os.path.realpath(os.path.dirname(gitdir))
    return gitdir  # bare repo: the gitdir is the repo itself


def resolveTabColorName(workdir: str, repoPrefs) -> str:
    """
    Resolve the effective tab color name for a worktree, or "" for no dot.
    repoPrefs is a RepoPrefs (or None for an unloaded tab, where only the
    repo binding can be honored).
    """
    override = repoPrefs.tabColorOverride if repoPrefs is not None else ""
    if override == OVERRIDE_NONE:
        return ""
    if override in TAB_PALETTE:
        return override
    binding = settings.prefs.tabColorBindings.get(repoBindingKey(workdir), "")
    if binding in TAB_PALETTE:
        return binding
    return ""


def tabDotIcon(colorName: str) -> QIcon:
    """Round dot icon for a palette color. Cached by stockIcon."""
    fill = TAB_PALETTE[colorName]
    outline = fill.darker(140)
    return stockIcon("tab-dot", f"red={fill.name()} black={outline.name()}")
```

- [ ] **Step 5: Add the pref fields.**

In `gitfourchette/settings.py`, inside `class Prefs`, `_category_hidden` section, right after `refSortClearTimestamp : int = 0` (~line 202), add one line (staged here until Task 3 gives it a Settings control):

```python
    tabColorBindings            : dict[str, str]        = dataclasses.field(default_factory=dict)
```

In `gitfourchette/repoprefs.py`, inside `class RepoPrefs`, after `customKeyFile: str = ""` (~line 42), add:

```python
    tabColorOverride: str = ""
```

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: 7 passed.

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 999 passed, 16 skipped, 0 failed (baseline 992 + 7 new).

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tabcolors.py gitfourchette/assets/icons/tab-dot.svg test/test_tabcolors.py gitfourchette/settings.py gitfourchette/repoprefs.py
git commit -m "feat: tab color model (repo bindings, worktree overrides, dot icons)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Tab Color submenu + colored dots on tabs

**Files:**
- Modify: `gitfourchette/tabcolors.py` (add `makeTabColorSubmenu`)
- Modify: `gitfourchette/mainwindow.py` (submenu in `generateTabContextMenu` ~line 528; new `refreshTabColors` method; tail call in `refreshAllTabTexts` ~line 932; call in `onTabCurrentWidgetChanged` ~line 484; branch in `onApplyPrefs` ~line 1131; import)
- Modify: `gitfourchette/toolbox/qtabwidget2.py` (thin `setTabIcon` wrapper next to `setTabTooltip` ~line 354)
- Test: `test/test_tabcolors.py` (append integration tests)

**Interfaces:**
- Consumes from Task 1: `TAB_PALETTE`, `OVERRIDE_NONE`, `repoBindingKey`, `resolveTabColorName`, `tabDotIcon`, both pref fields.
- Produces: `tabcolors.makeTabColorSubmenu(parentMenu, workdir, repoPrefs, refresh, openSettings) -> QMenu` (objectNames `MWTabColorMenu`, `MWTabColorWorktreeMenu`); `MainWindow.refreshTabColors()`; `QTabWidget2.setTabIcon(i, icon)`. Menu captions (Task 3 tests navigate them): top level `Tab &Color` → swatches `&Red &Orange &Yellow &Green &Teal &Blue &Purple Gr&ay`, `&No Color`, separator, `Only This &Worktree` (swatches + `&No Color` + `A&uto`), separator, `&Manage Tab Colors…`.

- [ ] **Step 1: Write the failing tests** — append to `test/test_tabcolors.py`:

```python
def _dotKey(colorName: str) -> int:
    return tabcolors.tabDotIcon(colorName).cacheKey()


def _tabIconKey(mainWindow, i: int):
    icon = mainWindow.tabs.tabs.tabIcon(i)
    return None if icon.isNull() else icon.cacheKey()


def _openMainAndLinkedWorktree(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    runShellScript("git worktree add ../LinkedWT", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    rwMain = mainWindow.openRepo(wd)
    rwChild = mainWindow.openRepo(linked)
    assert mainWindow.tabs.indexOf(rwMain) == 0
    assert mainWindow.tabs.indexOf(rwChild) == 1
    return wd, linked, rwMain, rwChild


def testBindWholeRepoFromMainTab(tempDir, mainWindow):
    from gitfourchette import settings
    wd, linked, rwMain, rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    assert _tabIconKey(mainWindow, 0) is None
    assert _tabIconKey(mainWindow, 1) is None

    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/orange")

    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "orange"}
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")

    # Regenerated menu shows the current binding checked, on both tabs
    for i in range(2):
        menu = mainWindow.generateTabContextMenu(i)
        assert findMenuAction(menu, "tab color/orange").isChecked()
        assert not findMenuAction(menu, "tab color/no color").isChecked()

    # No Color removes the binding and both dots
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/no color")
    assert settings.prefs.tabColorBindings == {}
    assert _tabIconKey(mainWindow, 0) is None
    assert _tabIconKey(mainWindow, 1) is None


def testBindWholeRepoFromChildWorktreeTab(tempDir, mainWindow):
    from gitfourchette import settings
    wd, linked, rwMain, rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)

    menu = mainWindow.generateTabContextMenu(1)  # child worktree's tab
    triggerMenuAction(menu, "tab color/teal")

    # Keyed to the MAIN root even when set from the child's tab
    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "teal"}
    assert _tabIconKey(mainWindow, 0) == _dotKey("teal")
    assert _tabIconKey(mainWindow, 1) == _dotKey("teal")


def testWorktreeOverride(tempDir, mainWindow):
    wd, linked, rwMain, rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/orange")

    # Override child to "none": child dot disappears, main keeps it
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color/only this worktree/no color")
    assert rwChild.repoModel.prefs.tabColorOverride == "none"
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) is None

    # Override child to blue: child blue, main orange
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color/only this worktree/blue")
    assert rwChild.repoModel.prefs.tabColorOverride == "blue"
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("blue")
    menu = mainWindow.generateTabContextMenu(1)
    assert findMenuAction(menu, "tab color/only this worktree/blue").isChecked()

    # Back to Auto: child follows the binding again
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color/only this worktree/auto")
    assert rwChild.repoModel.prefs.tabColorOverride == ""
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")
    menu = mainWindow.generateTabContextMenu(1)
    assert findMenuAction(menu, "tab color/only this worktree/auto").isChecked()


def testUnloadedStubTabKeepsBindingDot(tempDir, mainWindow):
    from gitfourchette.forms.repostub import RepoStub
    wd, linked, rwMain, rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/purple")

    mainWindow.tabs.setCurrentIndex(1)
    mainWindow.unloadOtherTabs(1)  # tab 0 becomes a RepoStub
    assert isinstance(mainWindow.tabs.widget(0), RepoStub)
    assert _tabIconKey(mainWindow, 0) == _dotKey("purple")

    # Binding actions still work on a stub tab; worktree submenu is disabled
    menu = mainWindow.generateTabContextMenu(0)
    worktreeAction = findMenuAction(menu, "tab color/only this worktree")
    assert not worktreeAction.isEnabled()
    triggerMenuAction(menu, "tab color/green")
    assert _tabIconKey(mainWindow, 0) == _dotKey("green")


def testTabColorPersistenceAcrossReopen(tempDir, mainWindow):
    wd, linked, rwMain, rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/orange")
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color/only this worktree/blue")

    mainWindow.closeTab(1)  # writes the child's RepoPrefs (tabColorOverride)
    mainWindow.closeTab(0)
    assert mainWindow.tabs.count() == 0

    mainWindow.openRepo(wd)
    mainWindow.openRepo(linked)
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("blue")


def testUrgentIconWinsUntilTabActivated(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    wd2 = unpackRepo(tempDir, renameTo="OtherRepo")
    mainWindow.openRepo(wd)
    mainWindow.openRepo(wd2)  # tab 1 is now current

    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/red")
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")

    # Urgent icon takes over the icon slot on the background tab
    mainWindow.tabs.requestAttention(0)
    urgentKey = _tabIconKey(mainWindow, 0)
    assert urgentKey is not None
    assert urgentKey != _dotKey("red")

    # A refresh must NOT stomp the urgent icon while the flag is set
    mainWindow.refreshTabColors()
    assert _tabIconKey(mainWindow, 0) == urgentKey

    # Activating the tab clears the urgent icon and restores the dot
    mainWindow.tabs.setCurrentIndex(0)
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: Task 1's 7 tests pass; the 6 new tests FAIL (`KeyError: didn't find menu 'tab color/...'`).

- [ ] **Step 3: Add the submenu builder to `gitfourchette/tabcolors.py`** (append; also add `from collections.abc import Callable` to the imports):

```python
def _swatchCaptions() -> dict[str, str]:
    return {
        "red": _("&Red"),
        "orange": _("&Orange"),
        "yellow": _("&Yellow"),
        "green": _("&Green"),
        "teal": _("&Teal"),
        "blue": _("&Blue"),
        "purple": _("&Purple"),
        "gray": _("Gr&ay"),
    }


def makeTabColorSubmenu(
        parentMenu: QMenu,
        workdir: str,
        repoPrefs,
        refresh: Callable[[], None],
        openSettings: Callable[[], None],
) -> QMenu:
    """
    Build the "Tab Color" submenu for a repo tab's context menu.
    repoPrefs is the tab's RepoPrefs, or None for an unloaded tab (worktree
    overrides live in the repo's prefs, so that submenu is disabled then).
    """
    bindingKey = repoBindingKey(workdir)
    currentBinding = settings.prefs.tabColorBindings.get(bindingKey, "")
    currentOverride = repoPrefs.tabColorOverride if repoPrefs is not None else ""

    submenu = QMenu(_("Tab &Color"), parentMenu)
    submenu.setObjectName("MWTabColorMenu")

    def setBinding(name: str):
        if name:
            settings.prefs.tabColorBindings[bindingKey] = name
        else:
            settings.prefs.tabColorBindings.pop(bindingKey, None)
        settings.prefs.setDirty()
        settings.prefs.write()
        refresh()

    def setOverride(value: str):
        repoPrefs.tabColorOverride = value
        repoPrefs.setDirty()
        refresh()

    captions = _swatchCaptions()

    for name in TAB_PALETTE:
        swatch = submenu.addAction(tabDotIcon(name), captions[name])
        swatch.setCheckable(True)
        swatch.setChecked(currentBinding == name)
        swatch.triggered.connect(lambda checked=False, n=name: setBinding(n))

    noColor = submenu.addAction(_("&No Color"))
    noColor.setCheckable(True)
    noColor.setChecked(not currentBinding)
    noColor.triggered.connect(lambda: setBinding(""))

    submenu.addSeparator()

    worktreeMenu = submenu.addMenu(_("Only This &Worktree"))
    worktreeMenu.setObjectName("MWTabColorWorktreeMenu")
    if repoPrefs is None:
        # Disable at the action level: that's what the parent menu displays
        # and what findMenuAction/isEnabled consult.
        worktreeMenu.menuAction().setEnabled(False)
    else:
        for name in TAB_PALETTE:
            swatch = worktreeMenu.addAction(tabDotIcon(name), captions[name])
            swatch.setCheckable(True)
            swatch.setChecked(currentOverride == name)
            swatch.triggered.connect(lambda checked=False, n=name: setOverride(n))
        wtNoColor = worktreeMenu.addAction(_("&No Color"))
        wtNoColor.setCheckable(True)
        wtNoColor.setChecked(currentOverride == OVERRIDE_NONE)
        wtNoColor.triggered.connect(lambda: setOverride(OVERRIDE_NONE))
        wtAuto = worktreeMenu.addAction(_("A&uto"))  # &A is taken by Gr&ay
        wtAuto.setCheckable(True)
        wtAuto.setChecked(currentOverride not in TAB_PALETTE and currentOverride != OVERRIDE_NONE)
        wtAuto.triggered.connect(lambda: setOverride(""))

    submenu.addSeparator()
    manage = submenu.addAction(_("&Manage Tab Colors…"))
    manage.triggered.connect(lambda: openSettings())

    return submenu
```

- [ ] **Step 4: Add the `setTabIcon` wrapper** in `gitfourchette/toolbox/qtabwidget2.py`, right after `setTabTooltip` (~line 355):

```python
    def setTabIcon(self, i: int, icon: QIcon):
        self.tabs.setTabIcon(i, icon)
```

- [ ] **Step 5: Wire up MainWindow** in `gitfourchette/mainwindow.py`:

(a) Add to the import block (alphabetical, near `from gitfourchette import tasks`):

```python
from gitfourchette import tabcolors
```

(b) In `generateTabContextMenu` (~line 528), split the existing `ActionDef.addToQMenu` call to insert the submenu between the repoless actions and "Configure Tabs…". Replace the whole call with:

```python
        ActionDef.addToQMenu(
            menu,
            ActionDef(_("Close Tab"), lambda: self.closeTab(i), shortcuts=QKeySequence.StandardKey.Close),
            ActionDef(_("Close Other Tabs"), lambda: self.closeOtherTabs(i), enabled=self.tabs.count() > 1),
            ActionDef(_("Unload Other Tabs"), lambda: self.unloadOtherTabs(i), enabled=self.tabs.count() > 1 and anyOtherLoadedTabs),
            ActionDef.SEPARATOR,
            *self.repolessActions(widget.workdir),
            ActionDef.SEPARATOR,
        )

        repoPrefs = widget.repoModel.prefs if isinstance(widget, RepoWidget) else None
        menu.addMenu(tabcolors.makeTabColorSubmenu(
            menu, widget.workdir, repoPrefs,
            refresh=self.refreshTabColors,
            openSettings=lambda: GFApplication.instance().openPrefsDialog("tabColorBindings")))

        ActionDef.addToQMenu(
            menu,
            ActionDef.SEPARATOR,
            ActionDef(_("Configure Tabs…"), lambda: GFApplication.instance().openPrefsDialog("tabCloseButton")),
        )
```

(c) Add the refresh method (next to `refreshAllTabTexts`, ~line 908):

```python
    def refreshTabColors(self):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if widget is None:
                continue
            if widget.property(QTabWidget2.UrgentPropertyName):
                continue  # urgent icon owns the slot until the tab is activated
            repoPrefs = widget.repoModel.prefs if isinstance(widget, RepoWidget) else None
            colorName = tabcolors.resolveTabColorName(widget.workdir, repoPrefs)
            icon = tabcolors.tabDotIcon(colorName) if colorName else QIcon()
            self.tabs.setTabIcon(i, icon)
```

(d) At the very end of `refreshAllTabTexts` (after the `setTabText` loop, ~line 932), add:

```python
        self.refreshTabColors()
```

(e) In `onTabCurrentWidgetChanged` (~line 484), add as the FIRST line of the method body (it must run before the early returns for zero tabs / RepoStub, to restore the dot after QTabWidget2's urgent-icon clear):

```python
        self.refreshTabColors()
```

(f) In `onApplyPrefs` (~line 1131), add at the end of the method:

```python
        if "tabColorBindings" in changedKeys:
            self.refreshTabColors()
```

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: 13 passed.

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 1005 passed, 16 skipped, 0 failed. If any pre-existing test fails on the tab context menu shape or tab icons, STOP and report DONE_WITH_CONCERNS with the failure — do not silently adapt unrelated tests.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tabcolors.py gitfourchette/mainwindow.py gitfourchette/toolbox/qtabwidget2.py test/test_tabcolors.py
git commit -m "feat: tab color submenu + colored dots on repo tabs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Settings control for bindings (read/remove list)

**Files:**
- Modify: `gitfourchette/settings.py` (move `tabColorBindings` line from `_category_hidden` to `_category_tabs`, after `autoHideTabs` ~line 163)
- Modify: `gitfourchette/forms/prefsdialog.py` (dispatch branch in `makeControlWidget` ~line 343 + new `tabColorBindingsControl` method)
- Modify: `gitfourchette/trtables.py` (one caption line near the other tab captions ~line 462)
- Test: `test/test_tabcolors.py` (append)

**Interfaces:**
- Consumes: `tabcolors.TAB_PALETTE`, `tabcolors.tabDotIcon`, menu caption `&Manage Tab Colors…` (Task 2), `settings.prefs.tabColorBindings` (Task 1).
- Produces: PrefsDialog control with child objectNames `tabColorBindingsList` (QListWidget) and `tabColorBindingsRemove` (QPushButton); container auto-named `prefctl_tabColorBindings`. List items: dot icon, text `compactPath(path)`, `Qt.ItemDataRole.UserRole` = raw path.

- [ ] **Step 1: Write the failing tests** — append to `test/test_tabcolors.py`:

```python
def _bindOrange(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    mainWindow.openRepo(wd)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/orange")
    return wd


def testManageTabColorsOpensSettingsOnBindingsList(tempDir, mainWindow):
    _bindOrange(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color/manage tab colors")
    dlg = findQDialog(mainWindow, "settings")
    listWidget: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    assert listWidget is not None
    assert listWidget.count() == 1
    assert not listWidget.item(0).icon().isNull()
    dlg.reject()


def testRemoveBindingViaSettings(tempDir, mainWindow):
    from gitfourchette import settings
    wd = _bindOrange(tempDir, mainWindow)
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")

    dlg = GFApplication.instance().openPrefsDialog("tabColorBindings")
    listWidget: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    removeButton: QPushButton = dlg.findChild(QPushButton, "tabColorBindingsRemove")
    assert listWidget.count() == 1
    assert listWidget.item(0).data(Qt.ItemDataRole.UserRole) == os.path.realpath(wd)

    listWidget.setCurrentRow(0)
    removeButton.click()
    assert listWidget.count() == 0

    # Working-copy semantics: nothing applied until OK
    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "orange"}

    dlg.accept()
    assert settings.prefs.tabColorBindings == {}
    assert _tabIconKey(mainWindow, 0) is None


def testRemoveBindingCancelKeepsBinding(tempDir, mainWindow):
    from gitfourchette import settings
    wd = _bindOrange(tempDir, mainWindow)

    dlg = GFApplication.instance().openPrefsDialog("tabColorBindings")
    listWidget: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    removeButton: QPushButton = dlg.findChild(QPushButton, "tabColorBindingsRemove")
    listWidget.setCurrentRow(0)
    removeButton.click()
    dlg.reject()

    assert settings.prefs.tabColorBindings == {os.path.realpath(wd): "orange"}
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
```

Also add these imports to the top of `test/test_tabcolors.py` if not already present via `.util`:

```python
from gitfourchette.application import GFApplication
```

(`QListWidget`, `QPushButton`, `Qt` come in via `from .util import *`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: the 3 new tests FAIL (`tabColorBindingsList` not found / NotImplementedError is NOT expected yet because the field is still hidden — the dialog opens fine but has no such control). All previous tests still pass.

- [ ] **Step 3: Move the pref field.** In `gitfourchette/settings.py`, DELETE the `tabColorBindings` line from `_category_hidden` and add it to `_category_tabs` after `autoHideTabs` (~line 163):

```python
    _category_tabs              : int                   = 0
    tabCloseButton              : bool                  = True
    expandingTabs               : bool                  = True
    autoHideTabs                : bool                  = False
    tabColorBindings            : dict[str, str]        = dataclasses.field(default_factory=dict)
```

- [ ] **Step 4: Add the caption.** In `gitfourchette/trtables.py`, after `"autoHideTabs": ...` (~line 464), add:

```python
            "tabColorBindings": _("Tab colors"),
```

- [ ] **Step 5: Add the control to `gitfourchette/forms/prefsdialog.py`.**

(a) In `makeControlWidget`, add a branch before the generic `issubclass(valueType, enum.Enum)` fallthroughs (e.g. right after the `gitPath` branch):

```python
        elif key == "tabColorBindings":
            return self.tabColorBindingsControl(key, value)
```

(b) Add the method (e.g. after `colorblindControl`):

```python
    def tabColorBindingsControl(self, prefKey: str, prefValue: dict):
        from gitfourchette.tabcolors import TAB_PALETTE, tabDotIcon

        listWidget = QListWidget(self)
        listWidget.setObjectName("tabColorBindingsList")
        listWidget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        listWidget.setMinimumHeight(120)

        removeButton = QPushButton(_("Remo&ve Selected Binding"), self)
        removeButton.setObjectName("tabColorBindingsRemove")

        def refill():
            listWidget.clear()
            bindings = self.getMostRecentValue(prefKey)
            for path in sorted(bindings):
                colorName = bindings[path]
                icon = tabDotIcon(colorName) if colorName in TAB_PALETTE else QIcon()
                item = QListWidgetItem(icon, compactPath(path), listWidget)
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
            removeButton.setEnabled(listWidget.count() > 0)

        def onRemove():
            item = listWidget.currentItem()
            if item is None:
                return
            path = item.data(Qt.ItemDataRole.UserRole)
            newBindings = dict(self.getMostRecentValue(prefKey))
            newBindings.pop(path, None)
            self.assign(prefKey, newBindings)
            refill()

        removeButton.clicked.connect(onRemove)
        refill()
        return vBoxWidget(listWidget, removeButton)
```

Notes: `compactPath` comes from the existing `from gitfourchette.toolbox import *`. Never mutate the dict returned by `getMostRecentValue` in place — always copy (`dict(...)`) before editing, then `assign` (working-copy semantics; applied by `GFApplication._applyPrefs` on OK, which then triggers `MainWindow.onApplyPrefs` → `refreshTabColors`, wired in Task 2). There is deliberately no add/edit path — bindings are created from tabs.

- [ ] **Step 6: Run the new tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: 16 passed.

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 1008 passed, 16 skipped, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/settings.py gitfourchette/trtables.py gitfourchette/forms/prefsdialog.py test/test_tabcolors.py
git commit -m "feat: manage tab color bindings in Settings (read/remove list)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## After all tasks

- Final whole-branch review (superpowers:requesting-code-review), most capable model, with the Minor-findings roll-up from task reviews.
- Merge flow per the worktree recipe: merge `fork-main` into the feature branch, run combined suite in the worktree, then `git merge --ff-only` in the main checkout when its tree is clean.
- Manual GUI smoke (deferred to user): dot rendering in light/dark Breeze themes, swatch icons in the menu, Settings list look, urgent-icon interplay with a real background fetch.
