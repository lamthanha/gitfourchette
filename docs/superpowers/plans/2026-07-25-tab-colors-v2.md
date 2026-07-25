# Tab Colors v2 (Menu Split + Global Override Storage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved amendment to the tab-colors feature: worktree overrides move to a global dict (Settings-listable, stub-tab capable, with legacy migration), the tab context menu splits into Repository/This-Worktree scopes with an "Inherited (X)" entry and a provenance status row, and Settings gains a second list for overrides.

**Architecture:** All logic changes stay in `gitfourchette/tabcolors.py` (resolution, migration, menu builders) plus the same sanctioned upstream touchpoints as v1 (`settings.py`, `repoprefs.py` comment only, `mainwindow.py` one call site, `forms/prefsdialog.py`, `trtables.py`). Tests evolve in `test/test_tabcolors.py`.

**Spec:** `docs/superpowers/specs/2026-07-25-tab-colors-design.md`, section "Amendment (2026-07-25 evening)". The base feature (v1) is fully merged at `a2a3fd4b`; baseline suite 1008 passed / 16 skipped.

## Global Constraints

- Test runner prefix: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` from the worktree root. Full suite must be **0 failed** on top of baseline (1008 passed / 16 skipped).
- NO edits to `gitfourchette/tasks/__init__.py` or `taskbook.py`. Upstream churn limited to: `settings.py` (one field + staging move), `repoprefs.py` (comment on the legacy field only), `mainwindow.py` (one call-site change in `generateTabContextMenu`), `forms/prefsdialog.py` (generalize the existing control), `trtables.py` (two caption lines). Everything else in `tabcolors.py` and the test file.
- Override semantics unchanged: `""` = inherit binding, `"none"` = explicitly colorless, else palette color name. Resolution: override → binding → no dot. Unknown values degrade gracefully.
- Keys: binding key = realpath of main worktree root (unchanged, `repoBindingKey`); override key = **realpath of the worktree itself** (`os.path.realpath(workdir)`), applied at both write and read time.
- `repoBindingKey` observable behavior must NOT change (its unit tests must pass unmodified).
- Menu rules (amendment): split mode iff `repoHasLinkedWorktrees(workdir) or bool(override entry for this worktree)`. Single mode: one `Tab &Color` submenu (status row when applicable + binding swatches + `&No Color` + separator + `&Manage Tab Colors…`). Split mode: `Tab &Color: Repository` (same content) + `Tab Color: This &Worktree` (status row + override swatches + `&No Color` + `&Inherited (X)`). Status row: disabled action, dot icon when a color is in effect, text `{Color} — set for this worktree` / `{Color} — repository color` / `No color — set for this worktree`; omitted when no binding and no override. Em dash `—`, `_("...")` localization, mnemonics unique per (sub)menu.
- Legacy migration: on resolution with a loaded repo whose `repoPrefs.tabColorOverride` is non-empty → `tabColorOverrides.setdefault(realpath(workdir), value)`, clear the repo field, `setDirty()` both, write global prefs. Old repo JSONs must keep loading cleanly.
- TDD; one commit per task, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Verified codebase facts (from v1 execution — do not re-derive)

- `tabcolors.py` currently: `TAB_PALETTE` (8 names → QColor), `OVERRIDE_NONE = "none"`, `repoBindingKey(workdir)`, `resolveTabColorName(workdir, repoPrefs)` (reads `repoPrefs.tabColorOverride`), `tabDotIcon(name)`, `_swatchCaptions()`, `makeTabColorSubmenu(parentMenu, workdir, repoPrefs, refresh, openSettings)`.
- `mainwindow.py` `generateTabContextMenu` calls `menu.addMenu(tabcolors.makeTabColorSubmenu(menu, widget.workdir, repoPrefs, refresh=self.refreshTabColors, openSettings=...))` between two `ActionDef.addToQMenu` blocks; `refreshTabColors()` passes `(widget.workdir, repoPrefs)` to `resolveTabColorName` per tab and skips urgent-flagged tabs.
- `forms/prefsdialog.py` has `tabColorBindingsControl(prefKey, prefValue)` (QListWidget `tabColorBindingsList` + QPushButton `tabColorBindingsRemove`, rows icon+`compactPath(path)`, UserRole=raw path, copy-then-`assign` working-copy semantics) dispatched via `elif key == "tabColorBindings"`.
- `settings.py`: `tabColorBindings` sits in `_category_tabs` after `autoHideTabs` (line ~164). Dict fields placed in a visible category REQUIRE a dispatch branch in `makeControlWidget` or PrefsDialog raises NotImplementedError — stage new dict fields in `_category_hidden` until their control lands.
- `trtables.py` `_init_prefKeys` has `"tabColorBindings": _("Tab colors"),` near line 465.
- `stripAccelerators` is exported by `gitfourchette.toolbox` (strips `&`).
- Test helpers in `test/test_tabcolors.py`: `_dotKey(name)`, `_tabIconKey(mainWindow, i)`, `_openMainAndLinkedWorktree(tempDir, mainWindow)` (returns `wd, linked, rwMain, rwChild`, tabs 0=main 1=child, child active), `_bindOrange(tempDir, mainWindow)`. `findMenuAction(menu, "part/leaf")` matches per path part with case-insensitive `re.search` on accelerator-stripped titles — note `"tab color"` also matches `"Tab Color: Repository"` (substring), and submenus are matched in creation order, so add the Repository menu FIRST.
- `RepoPrefs` JSON lives at `<gitdir>/gitfourchette.json`; `PrefsFile.load()` tolerates missing `_version` and skips unknown keys; `write()` skips default-valued fields. A test can pre-seed a legacy file by writing JSON into the repo's gitdir before `mainWindow.openRepo(wd)`.
- Under `APP_TESTMODE`, global prefs write under a per-test temp config wiped between tests; `mainWindow` fixture resets `settings.prefs` each test.
- Canned repo: `unpackRepo(tempDir)` (trailing slash on return); linked worktree via `runShellScript("git worktree add ../LinkedWT", wd)`; bare clone via `runShellScript("git clone --bare . ../Bare.git", wd)`. Tests that call `runShellScript` need the `mainWindow` fixture (GIT_CONFIG_GLOBAL).

---

### Task 1: Global override storage + legacy migration (menu structure unchanged)

**Files:**
- Modify: `gitfourchette/settings.py` (add `tabColorOverrides` in `_category_hidden`, after `refSortClearTimestamp`)
- Modify: `gitfourchette/repoprefs.py` (comment on the legacy field)
- Modify: `gitfourchette/tabcolors.py` (`resolveTabColorName` rewrite + `setOverride` body in `makeTabColorSubmenu`)
- Test: `test/test_tabcolors.py`

**Interfaces:**
- Consumes: everything listed in Verified facts.
- Produces (Tasks 2–3 rely on): `settings.prefs.tabColorOverrides: dict[str, str]` (worktree realpath → color name or `"none"`); `resolveTabColorName(workdir: str, repoPrefs=None) -> str` reading overrides from the global dict, with the legacy-migration hook; the `Only This Worktree` menu still gated on `repoPrefs is None` in this task (Task 2 removes that gating).

- [ ] **Step 1: Update/write the failing tests** in `test/test_tabcolors.py`:

(a) REPLACE `testResolveTabColorNamePrecedence` with:

```python
def testResolveTabColorNamePrecedence(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    key = tabcolors.repoBindingKey(wd)
    wtKey = os.path.realpath(wd)

    # No binding, no override
    assert tabcolors.resolveTabColorName(wd) == ""

    # Binding alone
    settings.prefs.tabColorBindings[key] = "orange"
    assert tabcolors.resolveTabColorName(wd) == "orange"

    # Explicit "none" override beats binding
    settings.prefs.tabColorOverrides[wtKey] = "none"
    assert tabcolors.resolveTabColorName(wd) == ""

    # Color override beats binding
    settings.prefs.tabColorOverrides[wtKey] = "blue"
    assert tabcolors.resolveTabColorName(wd) == "blue"

    # Unknown override value degrades to binding
    settings.prefs.tabColorOverrides[wtKey] = "bogus"
    assert tabcolors.resolveTabColorName(wd) == "orange"

    # Removing the override falls back to the binding
    del settings.prefs.tabColorOverrides[wtKey]
    assert tabcolors.resolveTabColorName(wd) == "orange"

    # Unknown binding value degrades to no dot
    settings.prefs.tabColorBindings[key] = "bogus"
    assert tabcolors.resolveTabColorName(wd) == ""


def testLegacyRepoPrefsOverrideMigratesToGlobalDict(tempDir, mainWindow):
    import json
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    # Pre-seed a legacy per-worktree override file (pre-redesign format)
    legacyFile = os.path.join(wd, ".git", "gitfourchette.json")
    with open(legacyFile, "w", encoding="utf-8") as f:
        json.dump({"tabColorOverride": "blue"}, f)

    rw = mainWindow.openRepo(wd)  # opening resolves colors -> triggers migration
    wtKey = os.path.realpath(wd)
    assert settings.prefs.tabColorOverrides == {wtKey: "blue"}
    assert rw.repoModel.prefs.tabColorOverride == ""
    assert _tabIconKey(mainWindow, 0) == _dotKey("blue")

    # Legacy value must not clobber an existing global entry (setdefault semantics)
    settings.prefs.tabColorOverrides[wtKey] = "teal"
    rw.repoModel.prefs.tabColorOverride = "red"
    assert tabcolors.resolveTabColorName(wd, rw.repoModel.prefs) == "teal"
    assert rw.repoModel.prefs.tabColorOverride == ""
```

(b) In `testWorktreeOverride`, replace the three `rwChild.repoModel.prefs.tabColorOverride == ...` assertions with global-dict assertions (`from gitfourchette import settings` at the top of the test):

```python
    assert settings.prefs.tabColorOverrides.get(os.path.realpath(linked)) == "none"
```
```python
    assert settings.prefs.tabColorOverrides.get(os.path.realpath(linked)) == "blue"
```
```python
    assert os.path.realpath(linked) not in settings.prefs.tabColorOverrides
```

(The menu paths `tab color/only this worktree/...` stay unchanged in this task.)

- [ ] **Step 2: Run tests to verify the new/changed ones fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: `testResolveTabColorNamePrecedence` FAILS (AttributeError: no `tabColorOverrides`), `testLegacyRepoPrefsOverrideMigratesToGlobalDict` FAILS, `testWorktreeOverride` FAILS on the dict assertion. Others pass.

- [ ] **Step 3: Add the global field.** In `gitfourchette/settings.py`, `_category_hidden`, right after `refSortClearTimestamp` (staged here until Task 3 gives it a Settings control):

```python
    tabColorOverrides           : dict[str, str]        = dataclasses.field(default_factory=dict)
```

- [ ] **Step 4: Mark the RepoPrefs field as legacy.** In `gitfourchette/repoprefs.py`, replace the line `tabColorOverride: str = ""` with:

```python
    # Legacy (pre-2026-07-25 redesign): superseded by Prefs.tabColorOverrides.
    # Kept so old files load; migrated & cleared by tabcolors.resolveTabColorName.
    tabColorOverride: str = ""
```

- [ ] **Step 5: Rewrite resolution + override write path in `gitfourchette/tabcolors.py`.**

Replace `resolveTabColorName` with:

```python
def resolveTabColorName(workdir: str, repoPrefs=None) -> str:
    """
    Resolve the effective tab color name for a worktree, or "" for no dot.
    repoPrefs (the tab's RepoPrefs, if loaded) is only consulted to migrate a
    legacy per-worktree override into the global dict.
    """
    wtKey = os.path.realpath(workdir)

    # Legacy migration: pre-redesign builds stored the override in the
    # worktree's own gitfourchette.json.
    if repoPrefs is not None and repoPrefs.tabColorOverride:
        settings.prefs.tabColorOverrides.setdefault(wtKey, repoPrefs.tabColorOverride)
        repoPrefs.tabColorOverride = ""
        repoPrefs.setDirty()
        settings.prefs.setDirty()
        settings.prefs.write()

    override = settings.prefs.tabColorOverrides.get(wtKey, "")
    if override == OVERRIDE_NONE:
        return ""
    if override in TAB_PALETTE:
        return override
    binding = settings.prefs.tabColorBindings.get(repoBindingKey(workdir), "")
    if binding in TAB_PALETTE:
        return binding
    return ""
```

In `makeTabColorSubmenu`, replace the `currentOverride` line and the `setOverride` closure with:

```python
    wtKey = os.path.realpath(workdir)
    currentOverride = settings.prefs.tabColorOverrides.get(wtKey, "")
```

```python
    def setOverride(value: str):
        if value:
            settings.prefs.tabColorOverrides[wtKey] = value
        else:
            settings.prefs.tabColorOverrides.pop(wtKey, None)
        settings.prefs.setDirty()
        settings.prefs.write()
        refresh()
```

(Keep the `repoPrefs is None → worktreeMenu.menuAction().setEnabled(False)` gating for now; Task 2 removes it. `repoPrefs` stays a parameter — it feeds the migration via the `resolveTabColorName` calls in `refreshTabColors`.)

- [ ] **Step 6: Run the test file**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: 17 passed.

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 1009 passed, 16 skipped, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/settings.py gitfourchette/repoprefs.py gitfourchette/tabcolors.py test/test_tabcolors.py
git commit -m "feat: move worktree tab-color overrides to global prefs (with legacy migration)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Menu split, Inherited (X), provenance status row

**Files:**
- Modify: `gitfourchette/tabcolors.py` (add `_commonGitDir`, `repoHasLinkedWorktrees`, `_effectiveStatus`, `_addStatusRow`; replace `makeTabColorSubmenu` with `makeTabColorMenus`)
- Modify: `gitfourchette/mainwindow.py` (call-site change only)
- Test: `test/test_tabcolors.py`

**Interfaces:**
- Consumes: Task 1's `tabColorOverrides` + `resolveTabColorName(workdir, repoPrefs=None)`.
- Produces: `repoHasLinkedWorktrees(workdir: str) -> bool`; `makeTabColorMenus(parentMenu, workdir, repoPrefs, refresh, openSettings) -> list[QMenu]` returning 1 menu (`MWTabColorMenu`, title `Tab &Color`) in single mode or 2 menus (`Tab &Color: Repository` + `MWTabColorWorktreeMenu` titled `Tab Color: This &Worktree`) in split mode. Menu captions Task 3 tests rely on: `&Manage Tab Colors…` stays in the repository-scope menu.
- `repoBindingKey` behavior unchanged (its existing unit tests must pass unmodified).

- [ ] **Step 1: Update/write the failing tests** in `test/test_tabcolors.py`:

(a) ADD new tests:

```python
def testSingleWorktreeRepoHasFlatColorMenu(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    mainWindow.openRepo(wd)
    menu = mainWindow.generateTabContextMenu(0)
    # Exactly one color menu, plainly titled — no worktree scope shown
    assert findMenuAction(menu, "^tab color$") is not None
    with pytest.raises(KeyError):
        findMenuAction(menu, "this worktree")
    triggerMenuAction(menu, "tab color/red")
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")


def testMultiWorktreeRepoSplitsColorMenus(tempDir, mainWindow):
    wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    assert findMenuAction(menu, "tab color: repository") is not None
    assert findMenuAction(menu, "tab color: this worktree") is not None
    # Repository scope binds the whole repo
    triggerMenuAction(menu, "tab color: repository/orange")
    assert _tabIconKey(mainWindow, 0) == _dotKey("orange")
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")
    # Worktree scope overrides only this worktree
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: this worktree/blue")
    assert _tabIconKey(mainWindow, 0) == _dotKey("blue")
    assert _tabIconKey(mainWindow, 1) == _dotKey("orange")


def testInheritedEntryShowsBindingColor(tempDir, mainWindow):
    wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: repository/green")

    menu = mainWindow.generateTabContextMenu(1)
    inherited = findMenuAction(menu, r"tab color: this worktree/inherited \(green\)")
    assert inherited.isChecked()
    assert not inherited.icon().isNull()

    # Override then return to inherited
    triggerMenuAction(menu, "tab color: this worktree/red")
    menu = mainWindow.generateTabContextMenu(1)
    assert not findMenuAction(menu, r"tab color: this worktree/inherited").isChecked()
    triggerMenuAction(menu, r"tab color: this worktree/inherited")
    assert _tabIconKey(mainWindow, 1) == _dotKey("green")

    # Without a binding, the label says Inherited (No Color)
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: repository/no color")
    menu = mainWindow.generateTabContextMenu(1)
    assert findMenuAction(menu, r"tab color: this worktree/inherited \(no color\)") is not None


def testStatusRowShowsEffectiveColorAndProvenance(tempDir, mainWindow):
    wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    # No binding, no override: no status row anywhere
    menu = mainWindow.generateTabContextMenu(0)
    with pytest.raises(KeyError):
        findMenuAction(menu, "tab color: repository/repository color")

    triggerMenuAction(menu, "tab color: repository/green")
    menu = mainWindow.generateTabContextMenu(0)
    status = findMenuAction(menu, "tab color: repository/green — repository color")
    assert not status.isEnabled()
    assert not status.icon().isNull()

    triggerMenuAction(menu, "tab color: this worktree/red")
    menu = mainWindow.generateTabContextMenu(0)
    for scope in ("repository", "this worktree"):
        status = findMenuAction(menu, f"tab color: {scope}/red — set for this worktree")
        assert not status.isEnabled()

    # "none" override reads as No color, set for this worktree
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: this worktree/no color")
    menu = mainWindow.generateTabContextMenu(0)
    assert findMenuAction(menu, "tab color: repository/no color — set for this worktree") is not None


def testOrphanOverrideKeepsWorktreeMenuOnSingleWorktreeRepo(tempDir, mainWindow):
    from gitfourchette import settings
    wd = unpackRepo(tempDir)
    settings.prefs.tabColorOverrides[os.path.realpath(wd)] = "red"
    mainWindow.openRepo(wd)
    assert _tabIconKey(mainWindow, 0) == _dotKey("red")
    # No linked worktrees, but the override must stay visible/clearable from the menu
    menu = mainWindow.generateTabContextMenu(0)
    assert findMenuAction(menu, "tab color: this worktree/red").isChecked()
    triggerMenuAction(menu, r"tab color: this worktree/inherited")
    assert _tabIconKey(mainWindow, 0) is None
    # Once cleared, the repo is back to a flat single menu
    menu = mainWindow.generateTabContextMenu(0)
    with pytest.raises(KeyError):
        findMenuAction(menu, "this worktree")


def testRepoHasLinkedWorktrees(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    assert not tabcolors.repoHasLinkedWorktrees(wd)
    runShellScript("git worktree add ../LinkedWT", wd)
    linked = os.path.join(os.path.dirname(os.path.normpath(wd)), "LinkedWT")
    assert tabcolors.repoHasLinkedWorktrees(wd)
    assert tabcolors.repoHasLinkedWorktrees(linked)
```

Add `import pytest` to the test file's imports if not already present.

(b) ADAPT existing tests to the split menu (these repos all have linked worktrees, so split mode is active):
- `testBindWholeRepoFromMainTab`: menu paths become `"tab color: repository/orange"` and `"tab color: repository/no color"`; the check-state assertions likewise.
- `testBindWholeRepoFromChildWorktreeTab`: `"tab color: repository/teal"`.
- `testWorktreeOverride`: paths become `"tab color: this worktree/no color"`, `"tab color: this worktree/blue"`, and Auto becomes `r"tab color: this worktree/inherited"`; the binding action path becomes `"tab color: repository/orange"`; checked-state assertions use the new paths.
- `testUnloadedStubTabKeepsBindingDot`: the stub's worktree menu is now fully functional (global storage). Replace the two `worktreeAction` lines with:

```python
    triggerMenuAction(menu, "tab color: this worktree/teal")
    assert _tabIconKey(mainWindow, 0) == _dotKey("teal")
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, r"tab color: this worktree/inherited")
```

  and change the final binding action to `triggerMenuAction(menu2, "tab color: repository/green")` where `menu2 = mainWindow.generateTabContextMenu(0)` (regenerate after the inherited click), keeping the final `_dotKey("green")` assertion. (Single-repo tests like `_bindOrange`-based ones and `testUrgentIconWinsUntilTabActivated` keep flat `"tab color/..."` paths — those repos have no linked worktrees.)
- `testTabColorPersistenceAcrossReopen`: paths `"tab color: repository/orange"` and `"tab color: this worktree/blue"`.

- [ ] **Step 2: Run tests to verify the new/changed ones fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: the 6 new tests FAIL (`KeyError: didn't find menu 'tab color: repository'` / missing `repoHasLinkedWorktrees`), and the adapted ones FAIL on the new paths. Unmodified tests still pass.

- [ ] **Step 3: Refactor gitdir helpers in `gitfourchette/tabcolors.py`.** Replace the body of `repoBindingKey` with a split into `_commonGitDir` + key derivation (behavior identical), and add `repoHasLinkedWorktrees`:

```python
def _commonGitDir(workdir: str) -> str:
    """
    Absolute path of the repo's common git dir: the main worktree's .git
    directory, or the repo dir itself for a bare repo. Best-effort for
    non-repos (returns a path whose basename is not ".git").
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
    elif not os.path.isdir(gitdir):
        return workdir  # bare repo (or not a repo at all)

    commondirFile = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondirFile):
        try:
            relCommon = Path(commondirFile).read_text("utf-8").strip()
        except OSError:
            relCommon = ""
        if relCommon:
            gitdir = os.path.realpath(os.path.join(gitdir, relCommon))

    return gitdir


def repoBindingKey(workdir: str) -> str:
    """
    Binding key for the repo containing this worktree: realpath of the main
    worktree's root (or of the repo dir itself for a bare repo).

    Parses .git gitfiles and commondir files directly (no pygit2) so it also
    works for unloaded tabs, and bind-time/resolve-time keys always agree.
    """
    gitdir = _commonGitDir(workdir)
    if os.path.basename(gitdir) == ".git":
        return os.path.realpath(os.path.dirname(gitdir))
    return gitdir


def repoHasLinkedWorktrees(workdir: str) -> bool:
    """True if the repo containing this worktree has any linked worktrees."""
    worktreesDir = os.path.join(_commonGitDir(workdir), "worktrees")
    try:
        return any(os.scandir(worktreesDir))
    except OSError:
        return False
```

(Note the deliberate parity: for bare repos `_commonGitDir` returns the repo dir, so `repoHasLinkedWorktrees` correctly checks `<bare>/worktrees`. The old `repoBindingKey` error paths returned `workdir`; the new composition returns the same values — its unit tests must pass unmodified.)

- [ ] **Step 4: Status helpers + menu builders in `gitfourchette/tabcolors.py`.** Add `stripAccelerators` to the toolbox import (`from gitfourchette.toolbox import stockIcon, stripAccelerators`). Replace `resolveTabColorName`'s tail so effective-state logic is shared, ADD the status helpers, and REPLACE `makeTabColorSubmenu` entirely with `makeTabColorMenus`:

```python
def _effectiveStatus(workdir: str) -> tuple[str, str]:
    """
    (colorName, provenance) for a worktree's effective tab color.
    colorName is "" for no dot; provenance is "override", "binding", or "".
    """
    override = settings.prefs.tabColorOverrides.get(os.path.realpath(workdir), "")
    if override == OVERRIDE_NONE:
        return "", "override"
    if override in TAB_PALETTE:
        return override, "override"
    binding = settings.prefs.tabColorBindings.get(repoBindingKey(workdir), "")
    if binding in TAB_PALETTE:
        return binding, "binding"
    return "", ""
```

In `resolveTabColorName`, replace everything after the migration block with:

```python
    color, _provenance = _effectiveStatus(workdir)
    return color
```

```python
def _plainColorName(name: str) -> str:
    return stripAccelerators(_swatchCaptions()[name])


def _addStatusRow(menu: QMenu, workdir: str):
    """Disabled first row stating the effective color and where it comes from."""
    color, provenance = _effectiveStatus(workdir)
    if not provenance:
        return
    if provenance == "override":
        if color:
            text = _("{0} — set for this worktree", _plainColorName(color))
        else:
            text = _("No color — set for this worktree")
    else:
        text = _("{0} — repository color", _plainColorName(color))
    status = menu.addAction(text)
    if color:
        status.setIcon(tabDotIcon(color))
    status.setEnabled(False)
    menu.addSeparator()


def makeTabColorMenus(
        parentMenu: QMenu,
        workdir: str,
        repoPrefs,
        refresh: Callable[[], None],
        openSettings: Callable[[], None],
) -> list[QMenu]:
    """
    Build the tab-color submenu(s) for a repo tab's context menu.
    Single-worktree repos get one flat "Tab Color" menu (repository scope).
    Repos with linked worktrees — or with an override recorded for this
    worktree — get "Tab Color: Repository" and "Tab Color: This Worktree".
    repoPrefs (or None for an unloaded tab) only feeds legacy migration.
    """
    resolveTabColorName(workdir, repoPrefs)  # legacy-migration hook

    wtKey = os.path.realpath(workdir)
    bindingKey = repoBindingKey(workdir)
    currentBinding = settings.prefs.tabColorBindings.get(bindingKey, "")
    currentOverride = settings.prefs.tabColorOverrides.get(wtKey, "")
    splitMode = repoHasLinkedWorktrees(workdir) or bool(currentOverride)
    captions = _swatchCaptions()

    def setBinding(name: str):
        if name:
            settings.prefs.tabColorBindings[bindingKey] = name
        else:
            settings.prefs.tabColorBindings.pop(bindingKey, None)
        settings.prefs.setDirty()
        settings.prefs.write()
        refresh()

    def setOverride(value: str):
        if value:
            settings.prefs.tabColorOverrides[wtKey] = value
        else:
            settings.prefs.tabColorOverrides.pop(wtKey, None)
        settings.prefs.setDirty()
        settings.prefs.write()
        refresh()

    repoTitle = _("Tab &Color: Repository") if splitMode else _("Tab &Color")
    repoMenu = QMenu(repoTitle, parentMenu)
    repoMenu.setObjectName("MWTabColorMenu")
    _addStatusRow(repoMenu, workdir)

    for name in TAB_PALETTE:
        swatch = repoMenu.addAction(tabDotIcon(name), captions[name])
        swatch.setCheckable(True)
        swatch.setChecked(currentBinding == name)
        swatch.triggered.connect(lambda checked=False, n=name: setBinding(n))

    noColor = repoMenu.addAction(_("&No Color"))
    noColor.setCheckable(True)
    noColor.setChecked(not currentBinding)
    noColor.triggered.connect(lambda: setBinding(""))

    repoMenu.addSeparator()
    manage = repoMenu.addAction(_("&Manage Tab Colors…"))
    manage.triggered.connect(lambda: openSettings())

    menus = [repoMenu]
    if not splitMode:
        return menus

    wtMenu = QMenu(_("Tab Color: This &Worktree"), parentMenu)
    wtMenu.setObjectName("MWTabColorWorktreeMenu")
    _addStatusRow(wtMenu, workdir)

    for name in TAB_PALETTE:
        swatch = wtMenu.addAction(tabDotIcon(name), captions[name])
        swatch.setCheckable(True)
        swatch.setChecked(currentOverride == name)
        swatch.triggered.connect(lambda checked=False, n=name: setOverride(n))

    wtNoColor = wtMenu.addAction(_("&No Color"))
    wtNoColor.setCheckable(True)
    wtNoColor.setChecked(currentOverride == OVERRIDE_NONE)
    wtNoColor.triggered.connect(lambda: setOverride(OVERRIDE_NONE))

    if currentBinding in TAB_PALETTE:
        inheritedCaption = _("&Inherited ({0})", _plainColorName(currentBinding))
    else:
        inheritedCaption = _("&Inherited (No Color)")
    inherited = wtMenu.addAction(inheritedCaption)
    if currentBinding in TAB_PALETTE:
        inherited.setIcon(tabDotIcon(currentBinding))
    inherited.setCheckable(True)
    inherited.setChecked(currentOverride not in TAB_PALETTE and currentOverride != OVERRIDE_NONE)
    inherited.triggered.connect(lambda: setOverride(""))

    menus.append(wtMenu)
    return menus
```

Mnemonic budgets (verify, don't take on faith): repo menu R/O/Y/G/T/B/P/A + N + M; worktree menu R/O/Y/G/T/B/P/A + N + I; parent context menu gains C and W beside existing O/T/E/Y/N.

- [ ] **Step 5: Update the call site in `gitfourchette/mainwindow.py`.** In `generateTabContextMenu`, replace the single `menu.addMenu(tabcolors.makeTabColorSubmenu(...))` statement with:

```python
        for colorMenu in tabcolors.makeTabColorMenus(
                menu, widget.workdir, repoPrefs,
                refresh=self.refreshTabColors,
                openSettings=lambda: GFApplication.instance().openPrefsDialog("tabColorBindings")):
            menu.addMenu(colorMenu)
```

- [ ] **Step 6: Run the test file**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: 23 passed.

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 1015 passed, 16 skipped, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add gitfourchette/tabcolors.py gitfourchette/mainwindow.py test/test_tabcolors.py
git commit -m "feat: split tab-color menu by scope, Inherited label, provenance status row

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Settings list for worktree overrides

**Files:**
- Modify: `gitfourchette/settings.py` (move `tabColorOverrides` from `_category_hidden` to `_category_tabs`, right after `tabColorBindings`)
- Modify: `gitfourchette/trtables.py` (change one caption, add one caption)
- Modify: `gitfourchette/forms/prefsdialog.py` (generalize the control for both dict prefs)
- Test: `test/test_tabcolors.py`

**Interfaces:**
- Consumes: Tasks 1–2 (`tabColorOverrides`, split menus).
- Produces: second Settings list with child objectNames `tabColorOverridesList` / `tabColorOverridesRemove` (bindings control keeps `tabColorBindingsList` / `tabColorBindingsRemove`).

- [ ] **Step 1: Write the failing tests** — append to `test/test_tabcolors.py`:

```python
def testWorktreeOverridesListedInSettings(tempDir, mainWindow):
    wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/green")
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/no color")

    dlg = GFApplication.instance().openPrefsDialog("tabColorOverrides")
    overridesList: QListWidget = dlg.findChild(QListWidget, "tabColorOverridesList")
    bindingsList: QListWidget = dlg.findChild(QListWidget, "tabColorBindingsList")
    assert bindingsList.count() == 1
    assert overridesList.count() == 1
    item = overridesList.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == os.path.realpath(linked)
    assert item.icon().isNull()  # "none" override: no dot icon
    dlg.reject()


def testRemoveOverrideViaSettingsRevertsToInherited(tempDir, mainWindow):
    from gitfourchette import settings
    wd, linked, _rwMain, _rwChild = _openMainAndLinkedWorktree(tempDir, mainWindow)
    menu = mainWindow.generateTabContextMenu(0)
    triggerMenuAction(menu, "tab color: repository/green")
    menu = mainWindow.generateTabContextMenu(1)
    triggerMenuAction(menu, "tab color: this worktree/red")
    assert _tabIconKey(mainWindow, 1) == _dotKey("red")

    dlg = GFApplication.instance().openPrefsDialog("tabColorOverrides")
    overridesList: QListWidget = dlg.findChild(QListWidget, "tabColorOverridesList")
    removeButton: QPushButton = dlg.findChild(QPushButton, "tabColorOverridesRemove")
    assert not overridesList.item(0).icon().isNull()  # red dot shown
    overridesList.setCurrentRow(0)
    removeButton.click()
    assert overridesList.count() == 0

    # Working copy: nothing applied until OK
    assert settings.prefs.tabColorOverrides == {os.path.realpath(linked): "red"}
    dlg.accept()
    assert settings.prefs.tabColorOverrides == {}
    assert _tabIconKey(mainWindow, 1) == _dotKey("green")  # back to inherited
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: the 2 new tests FAIL (`tabColorOverridesList` not found — the field is still hidden so the dialog opens without it). All previous tests pass.

- [ ] **Step 3: Move the field.** In `gitfourchette/settings.py`, DELETE the `tabColorOverrides` line from `_category_hidden` and add it in `_category_tabs` directly under `tabColorBindings`:

```python
    tabColorBindings            : dict[str, str]        = dataclasses.field(default_factory=dict)
    tabColorOverrides           : dict[str, str]        = dataclasses.field(default_factory=dict)
```

- [ ] **Step 4: Captions.** In `gitfourchette/trtables.py`, replace `"tabColorBindings": _("Tab colors"),` with:

```python
            "tabColorBindings": _("Repository tab colors"),
            "tabColorOverrides": _("Worktree tab colors"),
```

- [ ] **Step 5: Generalize the control in `gitfourchette/forms/prefsdialog.py`.**

Replace the dispatch branch `elif key == "tabColorBindings": return self.tabColorBindingsControl(key, value)` with:

```python
        elif key in ("tabColorBindings", "tabColorOverrides"):
            return self.tabColorTableControl(key, value)
```

Rename `tabColorBindingsControl` to `tabColorTableControl` and parameterize the objectNames and button caption. The full replacement method:

```python
    def tabColorTableControl(self, prefKey: str, prefValue: dict):
        from gitfourchette.tabcolors import TAB_PALETTE, tabDotIcon

        listWidget = QListWidget(self)
        listWidget.setObjectName(f"{prefKey}List")
        listWidget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        listWidget.setMinimumHeight(120)

        if prefKey == "tabColorBindings":
            removeCaption = _("Remo&ve Selected Binding")
        else:
            removeCaption = _("Rem&ove Selected Override")
        removeButton = QPushButton(removeCaption, self)
        removeButton.setObjectName(f"{prefKey}Remove")

        def refill():
            listWidget.clear()
            table = self.getMostRecentValue(prefKey)
            for path in sorted(table):
                colorName = table[path]
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
            newTable = dict(self.getMostRecentValue(prefKey))
            newTable.pop(path, None)
            self.assign(prefKey, newTable)
            refill()

        removeButton.clicked.connect(onRemove)
        refill()
        return vBoxWidget(listWidget, removeButton)
```

(The two lists sit on the same Settings page: `&V` vs `&O` button mnemonics must not collide with each other or other explicit `&` on that page — the three checkbox captions there carry no `&`.)

- [ ] **Step 6: Check the refresh hook.** `MainWindow.onApplyPrefs` currently refreshes on `"tabColorBindings"`; extend the condition (this is the ONE allowed mainwindow line change in this task):

```python
        if changedKeys & {"tabColorBindings", "tabColorOverrides"}:
            self.refreshTabColors()
```

- [ ] **Step 7: Run the test file**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_tabcolors.py -v`
Expected: 25 passed.

- [ ] **Step 8: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 1017 passed, 16 skipped, 0 failed.

- [ ] **Step 9: Commit**

```bash
git add gitfourchette/settings.py gitfourchette/trtables.py gitfourchette/forms/prefsdialog.py gitfourchette/mainwindow.py test/test_tabcolors.py
git commit -m "feat: list worktree tab-color overrides in Settings

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## After all tasks

- Final whole-branch review (superpowers:requesting-code-review) on the most capable model, fed the Minor-findings roll-up.
- Merge flow: worktree branch → combined suite → `git merge --ff-only` in the main checkout when clean.
- Manual GUI smoke (user): split menus on the real gitfourchette/multiselect pair, Inherited (X) label, status rows, two Settings lists, legacy red-override migration on first launch.
