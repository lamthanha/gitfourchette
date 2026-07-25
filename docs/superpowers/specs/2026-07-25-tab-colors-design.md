# Tab Color Dots with Repo Bindings — Design Spec

**Date:** 2026-07-25
**Status:** Design approved by user (conversation), pending spec review

## Goal

Fork-parity colored tabs, improved with automatic coloring by repo identity: a colored **dot** on each repo tab, driven by a global **repo binding** (main-worktree path → color, inherited by all linked worktrees) plus a per-worktree **override** for exceptions.

User decisions (2026-07-25 conversation):
- Visual: **colored dot** before the tab title (tab-icon slot; no custom painting).
- Binding UX: **tab context menu is the primary flow** (no path picker — an open tab is a valid repo by construction); **Settings shows a read/remove list** of bindings.
- Swatch click default: **binds the whole repo** (main root; all worktrees inherit); per-worktree action is nested.

## Model — one mechanism per semantic

- **Repo binding** — global `Prefs.tabColorBindings: dict[str, str]` mapping *realpath of the main worktree root* → color name. Colors the repo and all its linked worktrees. Created/changed from any of the repo's tabs; always keyed to the main root, even when set from a child worktree's tab.
- **Worktree override** — `RepoPrefs.tabColorOverride: str = ""` in the worktree's own gitdir JSON. `""` = Auto (follow binding), `"none"` = explicitly colorless despite a binding, otherwise a color name. This implements "color only this worktree".
- **Resolution:** override → repo binding → no dot. More specific wins; same repo in several tabs is consistent by construction. (The original idea of child-path *bindings* is deliberately dropped — the override covers that case; two mechanisms with identical effects would compete.)

## Palette

8 fixed colors reused from `gitfourchette/colors.py` (clrs.cc scheme — no new color constants): `red, orange, yellow, green, teal, blue, purple, gray`. Color *names* (strings) are the persisted values; hex stays in one place. No free color picker (future extension).

## Verified facts (fork tree at 292f6b2d + polish commits)

- `MainWindow.generateTabContextMenu(i)` (`mainwindow.py:517`, menu objectName `MWRepoTabContextMenu`) builds the tab context menu; `self.tabs` is a `QTabWidget2` whose inner `QTabBar2` is `self.tabs.tabs`.
- Tab icons already exist: `QTabWidget2` sets `stockIcon("urgent-tab")` on background tabs wanting attention (`qtabwidget2.py:468`) and **clears the icon with `setTabIcon(i, QIcon())`** when the tab is activated (`:311`). The dot shares this slot → stated precedence: urgent icon wins while set; the dot must be **re-applied on tab activation** (MainWindow already receives the current-changed signal).
- `PrefsFile` serializes `dict` fields (precedents: `History.repos`, `History.fileDialogPaths`, `Session.splitterSizes`). Global `Prefs` (settings.py:103) has category sentinels; **`_category_tabs` already exists** (`settings.py:160`) — the binding field and its Settings control live there.
- `PrefsDialog.makeControlWidget(key, value, caption)` (`prefsdialog.py:343`) dispatches per-field control widgets — the extension point for a custom bindings-list control. `PrefsDialog(parent, focusOn="")` supports opening focused on a key.
- `RepoPrefs` writes `gitfourchette.json` into the repo's gitdir; linked worktrees have their own gitdir → per-worktree storage is automatic.
- `Repo.commondir` property (`porcelain.py:748-758`) resolves the git common dir from a linked worktree. Main root derivation: `dirname(commondir)` when the commondir's basename is `.git`, else the commondir itself (bare fallback); apply `os.path.realpath` before use as a binding key.
- Tests: `mainWindow.openRepo(wd)`; `triggerMenuAction(menu, "path/leaf")` supports slash-separated submenu paths; scenarios via `runShellScript` (e.g. `git worktree add`).

## New module: `gitfourchette/tabcolors.py`

Per the fork's new-code-in-new-modules rule. Contents:
- `TAB_PALETTE`: ordered mapping color-name → `QColor` (from `colors.py`).
- `resolveTabColorName(repo, repoPrefs) -> str`: implements override → binding → `""`, using the identity rules above.
- `repoBindingKey(repo) -> str`: realpath of the main worktree root (commondir rule).
- `tabDotIcon(colorName) -> QIcon`: cached round-dot pixmap (antialiased filled circle, thin darker outline so yellow/gray stay visible on light themes; drawn at 2× for HiDPI).

## UI

**Tab context menu** — in `generateTabContextMenu`, a new "Tab &Color" submenu:
- 8 swatch actions (icon = dot, checkable; checked = current binding color) → set `tabColorBindings[repoBindingKey] = name`.
- "&No Color" → delete the binding.
- Separator, then "Only This &Worktree ▸": the 8 swatches + "&No Color" (`"none"`) + "&Auto" (`""`, default-checked) → set `tabColorOverride`.
- Separator, then "&Manage Tab Colors…" → `PrefsDialog(self, focusOn=<bindings key>)`.
- All captions `_("...")`, `…` typographic; mnemonics unique within each (sub)menu.

**Settings** — a custom control for `tabColorBindings` in the existing *Tabs* category: read-only list rows (dot icon + path) plus a single Remove button acting on the selected row. No add/edit path — creation happens from tabs. Follows PrefsDialog's working-copy semantics (changes applied like every other pref on OK).

**Refresh points** — one `MainWindow.refreshTabColors()` (or equivalent) applying `tabDotIcon(resolveTabColorName(...))` per tab, called: on tab added/repo opened; after any menu action above; on PrefsDialog accept; on tab activation (restores the dot after the urgent-icon clear).

## Persistence & edge cases

- Bindings ride the global settings file; overrides ride each worktree's `gitfourchette.json`; both survive restarts. Old files without the keys load with defaults (PrefsFile skips unknown/default fields symmetrically).
- Stale bindings (repo moved/deleted) never match and remain visible/removable in Settings.
- Symlinked/alternate path spellings collapse via realpath at both bind- and resolve-time.
- Removing a binding or setting an override refreshes all open tabs of that repo immediately.
- Bare repo opened directly: binding key = realpath(commondir); inheritance is moot but harmless.

## Testing

- Unit: `repoBindingKey` (main vs linked worktree vs symlinked path), `resolveTabColorName` precedence table (override/binding/none/auto), `tabDotIcon` caching.
- Integration (real menus, `unpackRepo` + `git worktree add` scenario):
  - Bind orange from the MAIN repo tab → both the main tab and the linked-worktree tab get the dot; binding key in `Prefs.tabColorBindings` is the main root.
  - Bind from the CHILD worktree's tab → same result (keyed to main root).
  - Override the child to `"none"` → child dot disappears, main keeps it; override to `blue` → child blue, main orange; back to Auto → child orange.
  - Persistence: close/reopen tabs → dots return.
  - Remove binding via the Settings control (or its backing handler) → dots clear on open tabs.
  - Urgent interplay: simulate the urgent icon then activate the tab → dot restored (not empty icon).
- Full suite bar: 0 failed on top of the then-current baseline.

## Constraints

- Test runner prefix: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`.
- NO edits to `tasks/__init__.py` / `taskbook.py`. New logic in `tabcolors.py`; upstream-file churn limited to: `settings.py` (one field), `repoprefs.py` (one field), `mainwindow.py` (submenu + refresh calls), `prefsdialog.py` (custom control dispatch), `qtabwidget2.py` (only if a thin icon wrapper is needed).
- TDD; commit per task with trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Coordinate with the parallel sidebar-polish session: this feature touches none of its files (sidebardelegate/test_sidebar), but plan execution must start from a clean tree state on those files.

## Out of scope (deliberate)

- Custom/arbitrary colors; auto-assigned palette rotation.
- Dots outside the tab bar (window menu, recent-repos list, taskbar).
- Per-branch or per-session colors.
- Migrating binding keys when a repo directory is moved.

## Amendment (2026-07-25 evening): menu split + global override storage

User smoke-test feedback (real gitfourchette + gitfourchette-multiselect worktree pair): the single
"Tab Color" submenu mixes the repo-binding scope and the worktree-override scope in one checkable
tree — the top-level swatches read as "this tab's color" but actually show the repo binding, and the
effective color's provenance is invisible. Also, worktree overrides (stored per-worktree in gitdir
JSON) cannot be listed in Settings. Approved redesign:

1. **Global override storage.** `RepoPrefs.tabColorOverride` is replaced by global
   `Prefs.tabColorOverrides: dict[str, str]` keyed by *worktree realpath* (values: color name or
   `"none"`). Consequences: Settings can list/remove every override; unloaded (RepoStub) tabs honor
   overrides; one storage mechanism for all color state. The RepoPrefs field is kept as a legacy
   shim: on first resolution of a loaded repo, a non-empty legacy value is migrated into the global
   dict (setdefault semantics) and cleared from the repo's JSON.
2. **Menu split.** When the repo has linked worktrees OR an override exists for this worktree
   (clearable-orphan rule), the tab context menu shows TWO submenus: "Tab Color: Repository"
   (swatches = binding, No Color, Manage Tab Colors…) and "Tab Color: This Worktree" (swatches =
   override, No Color = `"none"`, "Inherited (X)" = `""`). Single-worktree repos keep one flat
   "Tab Color" submenu (binding + Manage) — no worktree scope shown at all.
3. **"Inherited (X)" label** replaces "Auto": shows the inherited color's name and dot icon
   (e.g. "Inherited (Green)"), or "Inherited (No Color)" when the repo has no binding.
4. **Provenance status row**: a disabled first row in each color submenu showing the effective
   color dot + provenance — "Red — set for this worktree" / "Green — repository color" /
   "No color — set for this worktree". Omitted when neither binding nor override exists.
   The repository-scope menu stays enabled when overridden (it still governs other worktrees).
5. **Settings**: two list controls in the Tabs category — "Repository tab colors"
   (`tabColorBindings`) and "Worktree tab colors" (`tabColorOverrides`), same read/remove UX;
   override rows with value `"none"` show no dot icon. Removing an override row reverts that
   worktree to inherited.
