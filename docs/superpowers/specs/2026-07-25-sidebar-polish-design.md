# Sidebar Polish: Inline Star Button, Empty-Node Arrows, Bold Pin — Design Spec

**Date:** 2026-07-25
**Status:** Approved by user (conversation), pending spec review
**Follows:** `2026-07-25-ux-quickwins-starred-design.md` (starred branches shipped at `0c4067ea`/`e16a0461`)

## Goal

Three Fork-parity refinements to the sidebar, requested after the user's smoke test of the starred-branches batch:

1. **Inline star button** on branch rows, directly left of the existing eye ("Hide in Graph") button — visible on hover (hollow) and always visible when starred (filled). Clicking toggles the star. Remote branches stay starrable (user decision 2026-07-25). Applies equally to alias rows inside the Starred section (acts as unstar there).
2. **No expand/collapse arrow on childless nodes** — empty sections (Stashes, Submodules, Tags) and empty remotes (e.g. a never-fetched `upstream`) currently show a useless triangle; hide it, and make clicks on that band fall through to row selection. Arrow reappears automatically when the node gains children.
3. **Bold current branch inside the Starred section** — verified ALREADY WORKING (aliases share `node.data`, and the bold check keys on branch name vs `_checkedOut`; empirically confirmed incl. the `git-head` icon). Requirement: pin it with test assertions so a refactor can't silently regress it.

## Architecture

No new modules, tasks, or dialogs. Everything extends the existing delegate-painted button-band pattern (the eye) and the already-shipped `wantToggleStarNode`. NO edits to `tasks/__init__.py` or `taskbook.py`.

## Verified facts (fork tree at e16a0461)

- `SidebarDelegate.getClickZone(node, rect, x)` (`sidebardelegate.py:56-65`): pure function; zones checked in order Spacer → Expand (`node.mayHaveChildren() and x < rect.left()`) → Hide (`node.canBeHidden() and x > rect.right() - EYE_WIDTH - PADDING`) → Select. Constants `EXPAND_TRIANGLE_WIDTH = 6`, `PADDING = 4`, `EYE_WIDTH = 16` (`:24-26`).
- Triangle painting: `sidebardelegate.py:121` — `if node.mayHaveChildren() and not node.wantForceExpand():` (ignores actual child count; this is the empty-arrow bug).
- Eye painting: `sidebardelegate.py:225-240`; band reserved via `makeRoomForEye = mouseOver or isExplicitlyShown or isExplicitlyHidden or isImplicitlyHidden` (`:86-90`), `textRect.adjust(0, 0, -EYE_WIDTH, 0)` (`:161-162`). Ahead/behind indicators are suppressed whenever `makeRoomForEye` (`:170-172`), so hover-time bands never collide with them.
- Text font comes from `index.data(FontRole)` (`sidebardelegate.py:164`); bold for checked-out branch set in `SidebarModel.data()` (`sidebarmodel.py:704`), keyed on `branchName == self._checkedOut` — parent-independent, hence aliases already bold.
- Click plumbing (`sidebar.py`): `resolveClick(pos)` (`:811-819`) → `mousePressEvent` caches `(row, zone)` (`:829-843`); `mouseReleaseEvent` (`:845-880`) performs the action only if press/release row+zone match; `Hide` calls `self.wantHideNode(node, allButThis)`; `mouseDoubleClickEvent` re-routes non-Select zones back to `mousePressEvent` so rapid toggles never register as double-clicks (`:882-889`) — the star inherits this for free.
- `SidebarNode.canBeHidden()` = `kind in SidebarLayout.HideableItems` (`sidebarmodel.py:181-182`); the star helper mirrors this pattern.
- `Sidebar.wantToggleStarNode(node)` (shipped in `53cd569d`): mutates `prefs.starredRefs`, `setDirty()`, then `backUpSelection(); refresh(repoModel); restoreSelectionBackup()`.
- Icons: `stockIcon(iconId)` (`toolbox/iconbank.py:51`) resolves recolorable SVGs from `gitfourchette/assets/icons/<iconId>.svg` (e.g. the four `view-*.svg` eye icons). No star icon exists today.
- No existing test clicks a delegate zone; tests reach rows via `rw.sidebar.nodeToFilterIndex(node)` and `rw.sidebar.visualRect(index)` is available for coordinate math (pattern: `test_tasks_commit.py` sidebardclick usage).

## Feature 1: Inline star button

**Assets:** two new recolorable SVGs, `gitfourchette/assets/icons/star-filled.svg` and `star-outline.svg`, drawn in the same 16×16 viewBox style as the `view-*` icons (single path, `currentColor`-style fill handled by the recolor engine — copy the conventions of an existing icon in that directory). New files only — merge-clean vs upstream.

**Model (`sidebarmodel.py`):**
- `SidebarLayout.StarrableItems = [SidebarItem.LocalBranch, SidebarItem.RemoteBranch]` next to `HideableItems`.
- `SidebarNode.canBeStarred()` next to `canBeHidden()`, returning `self.kind in SidebarLayout.StarrableItems`. Alias nodes share these kinds → button appears in the Starred section too, filled, acting as unstar.

**Delegate (`sidebardelegate.py`):**
- `STAR_WIDTH = 16` next to `EYE_WIDTH`.
- In `paint()`: `isStarred = node.canBeStarred() and node.data in sidebarModel.repoModel.prefs.starredRefs`; `makeRoomForStar = isStarred or (mouseOver and node.canBeStarred())`. When set, shrink `textRect` by an additional `STAR_WIDTH` and draw `star-filled` (starred) or `star-outline` (hover, unstarred) in the band immediately left of the eye band — i.e. right-aligned bands in fixed order `[star][eye]`, each collapsing to zero width when unused. (Consequence, accepted in design review: a filled star on a non-hovered row sits at the far right edge and slides one slot left when the eye appears on hover.)
- `getClickZone`: after the existing Hide check, add: `elif node.canBeStarred() and x > rect.right() - EYE_WIDTH - STAR_WIDTH - PADDING: return SidebarClickZone.Star`. (Order matters: eye band wins the far right, star band the next 16px.) New enum member `SidebarClickZone.Star`.
- Note: zones are hover-independent (clicks imply hover, so the button is always visible when clickable). Non-starrable rows (remotes, folders, headers) fall through exactly as today.

**View (`sidebar.py`):** in `mouseReleaseEvent`, handle `SidebarClickZone.Star` → `self.wantToggleStarNode(node)`; `event.accept()`. No other plumbing (press-cache, double-click rerouting are generic).

**Tests (`test/test_sidebar.py`):**
- Pure-function zone tests: `getClickZone` on a starrable node returns Star/Hide/Select at representative x positions, and Select (not Star) for a `Remote` node at the star-band x.
- Behavior test: real `QTest.mouseClick` on the star band of a local-branch row (coords from `visualRect` right edge minus offsets) stars the ref (assert `starredRefs` + Starred section appears); second click on the alias row's star band unstars it.

## Feature 2: No arrow on childless nodes

**Delegate (`sidebardelegate.py`):**
- `:121` → `if node.mayHaveChildren() and node.children and not node.wantForceExpand():`
- `:60` (Expand zone) → `elif node.mayHaveChildren() and node.children and x < rect.left():`

`mouseReleaseEvent`'s Expand handler keeps its `mayHaveChildren` guard unchanged (unreachable for childless nodes once the zone is gone).

**Covers:** empty Stashes/Submodules/Tags headers, empty remotes (`upstream` symptom confirmed same root cause), any future empty section. Collapsed-header "(N)" count suffix unchanged. Arrow returns when children appear (paint + zone re-evaluate per event).

**Tests:** `getClickZone` returns Select (not Expand) at `x < rect.left()` for a childless header node, and Expand for one with children. Plus a behavior-level assertion that an empty remote / Stashes header row click at the arrow x-position merely selects.

## Feature 3: Pin the Starred bold behavior

Extend `testStarBranch` (or a sibling test): after starring the checked-out branch (`master` in the canned repo), assert via the model that the alias row's `FontRole` font `.bold()` is true and its `IconKey` is `git-head`, and that a non-checked-out starred branch's alias FontRole is falsy/not bold. No product code change.

## Constraints

- Test runner prefix: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Full suite must stay 0 failed (baseline 988 passed / 16 skipped at `e16a0461`).
- TDD per feature; commit per feature with trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- No new user-facing strings (icon-only button — no caption; tooltips out of scope, see below). No mnemonic changes.
- NO edits to `tasks/__init__.py` / `taskbook.py`.

## Out of scope (deliberate)

- Tooltip on the star button (the eye has none either on its band; menu entries carry the words).
- Star column/section reordering, star-count badges.
- Migrating stars on branch rename (still prunes per previous spec).
- Any change to the "(N)" collapsed-count suffix.

## Amendment (2026-07-25): star band rightmost, fixed slots

User-requested follow-up after smoke-testing Feature 1. The original design (star band left of the eye; each band collapsing to zero width when unused) made the persistent filled star **slide one slot left** when the eye appeared on hover. The user wants the star badge to stay put. Superseding decision: **the star owns the stable far-right slot; the eye sits in the slot immediately left of it; icons appear/disappear but never move horizontally.**

**New click zones (`getClickZone`, raw `visualRect` frame).** Order is Spacer → Expand → Star → Hide → Select (star now wins the far right, so it is checked before Hide). With `starBand = STAR_WIDTH if node.canBeStarred() else 0`:
- Starrable rows (LocalBranch, RemoteBranch): Star = `x > rect.right() - STAR_WIDTH - PADDING` (rightmost); Hide = `x > rect.right() - STAR_WIDTH - EYE_WIDTH - PADDING` (second band).
- Hideable-but-not-starrable rows (Remote, RefFolder): **unchanged** — no star band (`starBand = 0`), Hide = `x > rect.right() - EYE_WIDTH - PADDING`, eye flush right.

**New paint geometry — FIXED SLOTS.** On starrable rows, whenever **either** band is visible (`makeRoomForEye or makeRoomForStar`), reserve **both** slots (shrink `textRect` by `EYE_WIDTH + STAR_WIDTH`), even if only one icon is drawn. Icons draw into their fixed slots off `bandAnchor` (still captured before the indicator blocks clip `textRect`): eye at `bandAnchor` (`EYE_WIDTH` wide), star at `bandAnchor + EYE_WIDTH` (the far-right `STAR_WIDTH`). Eye still draws only when `makeRoomForEye`; star only when `makeRoomForStar`; the eye icon-choice chain is byte-identical to Feature 1. Non-starrable hideable rows keep the single eye slot flush right.

**Consequences (accepted; empirically pinned in `testStarPaintDoesNotCollideWithIndicatorsOrHideZone`):**
- A starred idle row and the same row hovered paint the star at the **pixel-identical** far-right position; likewise a hidden idle row and hovered row paint the eye at the pixel-identical slot-2 position. Nothing moves on hover.
- A hidden-but-unstarred idle row shows a "floating" eye with an empty star slot to its right (accepted look).
- Clicking the far-right slot on a starrable row now toggles the **star**, not hide; the hide-by-click tests target the eye's slot-2 position accordingly (`_eyeClickPos` helper).
