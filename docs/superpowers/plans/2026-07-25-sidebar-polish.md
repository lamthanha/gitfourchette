# Sidebar Polish (Star Button, Empty Arrows, Bold Pin) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inline star/unstar button on sidebar branch rows (left of the eye), no expand arrow on childless nodes, and test-pinning of the already-working bold treatment for the checked-out branch's Starred alias.

**Architecture:** Extends the delegate-painted button-band pattern (the eye) with a second collapsing band and a new click zone routed to the existing `wantToggleStarNode`; the empty-arrow fix is two one-line conditions in the same delegate. No new modules, tasks, or dialogs.

**Tech Stack:** Python ≥3.10, PyQt6, pytest + pytest-qt.

## Global Constraints

- Repo: `/home/admin/workspace.personal/gitfourchette`, branch `fork-main`. Spec: `docs/superpowers/specs/2026-07-25-sidebar-polish-design.md`.
- Test runner prefix (always): `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Full-suite bar: 0 failed (baseline 988 passed / 16 skipped at `e16a0461`).
- **NO edits to `tasks/__init__.py` or `taskbook.py`.** No new user-facing strings (icon-only button; no captions, no tooltips). No mnemonic changes.
- New SVG assets are new files only (merge-clean vs upstream); follow the drawing conventions of `gitfourchette/assets/icons/view-visible.svg` (16×16 viewBox, `stroke="gray"` / `fill:gray` — the recolor engine keys on gray).
- TDD: failing test first. Commit per task with trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Line numbers below refer to the tree at `2b655ac2`; verify anchors by content, not blindly by number.

## Key verified facts (fork tree at 2b655ac2)

- `SidebarClickZone` enum: `sidebardelegate.py:29-33` (`Invalid=0, Select=1, Expand=2, Hide=3`). Constants `EXPAND_TRIANGLE_WIDTH=6, PADDING=4, EYE_WIDTH=16` at `:24-26`.
- `getClickZone(node, rect, x)` (`:56-65`), checked in order Spacer → Expand (`x < rect.left()`) → Hide (`x > rect.right() - EYE_WIDTH - PADDING`) → Select. `resolveClick` (`sidebar.py:811-819`) passes the RAW `visualRect(index)` — the unindent adjustment only ever moves `rect.left()`, so right-edge band math is unaffected.
- Triangle painting gate: `sidebardelegate.py:121` — `if node.mayHaveChildren() and not node.wantForceExpand():`.
- Band reservation: `makeRoomForEye` computed at `:81-90` (only for `canBeHidden()` nodes; true on `mouseOver` or explicit/implicit hide states); `textRect` shrunk at `:160-162`; eye painted at `:225-239` at `r.setLeft(textRect.right())`, width `EYE_WIDTH`. Ahead/behind indicators are drawn only when NOT `makeRoomForEye` (`:167-206`) and right-align INTO `textRect`, so they never collide with reserved bands.
- Click plumbing (`sidebar.py`): `mousePressEvent` caches `(row, zone)`; `mouseReleaseEvent` acts only on press/release match — `Hide` → `self.wantHideNode(node, allButThis)`, `Expand` → expand/collapse (`:862-874`); unknown zones hit `warnings.warn` (`:875-876`) — the Star branch must be added BEFORE that fallthrough. `mouseDoubleClickEvent` re-routes non-Select zones to `mousePressEvent` (rapid toggling safe, no changes needed).
- `SidebarLayout.HideableItems` = sorted `[LocalBranch, Remote, RemoteBranch, RefFolder]` (`sidebarmodel.py:119-124`); `SidebarNode.canBeHidden()` at `:181-182`. `StarrableItems`/`canBeStarred()` mirror these.
- `Sidebar.wantToggleStarNode(node)` exists (shipped `53cd569d`): toggles `prefs.starredRefs`, `setDirty()`, `backUpSelection(); refresh(repoModel); restoreSelectionBackup()`. Clicking the star on an unselected row does NOT move selection (press with a non-Select zone never calls `setCurrentIndex`).
- `stockIcon(iconId)` resolves `assets:icons/<iconId>.svg` (`toolbox/iconbank.py:72-84`) through `RecolorSvgIconEngine`.
- Delegate `paint()` locals available at the insertion points: `node`, `sidebarModel`, `mouseOver`, `iconMode`, `option`, `textRect`. Starred lookup: `node.data in sidebarModel.repoModel.prefs.starredRefs` (`node.data` is the full refname on branch kinds).
- Canned repo (`unpackRepo`): `master` checked out; branches `master`, `no-parent`; remote `origin` with children; NO stashes, NO submodules (assert emptiness in tests before relying on it). `QTest`/`QPoint` are already in scope in `test/test_sidebar.py` (see the existing eye-click call `QTest.mouseClick(sb.viewport(), Qt.MouseButton.LeftButton, pos=rect.topRight())` at `test_sidebar.py:306` — copy that exact call form, `pos=` as keyword).
- Existing star tests: `test/test_sidebar.py::testStarBranch` (`:793-834`) — contains `folderAliasIndex` (display assertion, `:820-821`) and `masterAlias = next(...)` before the unstar trigger (`:824`).

---

### Task 1: No expand arrow on childless nodes

**Files:**
- Modify: `gitfourchette/sidebar/sidebardelegate.py` (`getClickZone` ~:60; triangle gate ~:121)
- Test: `test/test_sidebar.py` (append)

**Interfaces:**
- Consumes: `SidebarDelegate.getClickZone` (pure static), `findNodeByKind`, `nodeToFilterIndex`, `visualRect`.
- Produces: childless expandable nodes have no Expand zone and paint no triangle. (Task 2 edits the same function below the Expand line — keep the diff minimal.)

- [ ] **Step 1: Write the failing test**

Append to `test/test_sidebar.py` (add `SidebarDelegate`, `SidebarClickZone` to the test file's imports from `gitfourchette.sidebar.sidebardelegate` — check the top of the file and follow its import style):

```python
def testNoExpandZoneOnChildlessNodes(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    # Canned repo has no stashes: header exists but is childless
    stashes = rw.sidebar.findNodeByKind(SidebarItem.StashesHeader)
    assert not stashes.children
    rect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(stashes))
    arrowX = rect.left() - 5  # inside the expand-arrow band (x < rect.left())
    assert SidebarDelegate.getClickZone(stashes, rect, arrowX) == SidebarClickZone.Select

    # Sections that DO have children keep their Expand zone
    branches = rw.sidebar.findNodeByKind(SidebarItem.LocalBranchesHeader)
    assert branches.children
    brect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(branches))
    assert SidebarDelegate.getClickZone(branches, brect, brect.left() - 5) == SidebarClickZone.Expand

    # Behavior level: a real click on the (now nonexistent) arrow band of a
    # childless header merely selects the row and never expands it
    # (isExpanded is NOT asserted: Qt may keep a stored expanded flag on a
    # childless item; what matters is that the click selects the row.)
    stashesIndex = rw.sidebar.nodeToFilterIndex(stashes)
    QTest.mouseClick(rw.sidebar.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(rect.left() - 5, rect.center().y()))
    assert rw.sidebar.currentIndex() == stashesIndex
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py::testNoExpandZoneOnChildlessNodes -x -q`
Expected: FAIL — first `getClickZone` assert returns `Expand` (childless header still has the zone).

- [ ] **Step 3: Guard both sites on `node.children`**

`sidebardelegate.py` — Expand zone (~:60):

```python
        elif node.mayHaveChildren() and node.children and x < rect.left():
            return SidebarClickZone.Expand
```

Triangle gate (~:121):

```python
        if node.mayHaveChildren() and node.children and not node.wantForceExpand():
```

- [ ] **Step 4: Run the test + sidebar suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -q`
Expected: all PASS (no existing test asserts an arrow on an empty section).

- [ ] **Step 5: Commit**

```bash
git add gitfourchette/sidebar/sidebardelegate.py test/test_sidebar.py
git commit -m "fix: no expand arrow or expand zone on childless sidebar nodes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Inline star button

**Files:**
- Create: `gitfourchette/assets/icons/star-filled.svg`, `gitfourchette/assets/icons/star-outline.svg`
- Modify: `gitfourchette/sidebar/sidebarmodel.py` (`StarrableItems` after `HideableItems` ~:124; `canBeStarred` after `canBeHidden` ~:182)
- Modify: `gitfourchette/sidebar/sidebardelegate.py` (constant, enum member, `getClickZone`, `paint`)
- Modify: `gitfourchette/sidebar/sidebar.py` (`mouseReleaseEvent` Star branch)
- Test: `test/test_sidebar.py` (append)

**Interfaces:**
- Consumes: Task 1's edited `getClickZone` (insert the Star check AFTER the Hide check); existing `wantToggleStarNode(node)`; `stockIcon`.
- Produces: `SidebarClickZone.Star = 4`; `STAR_WIDTH = 16`; `SidebarNode.canBeStarred()`; `SidebarLayout.StarrableItems`. Band geometry from the right edge: eye `(right-EYE_WIDTH-PADDING, right]`, star `(right-EYE_WIDTH-STAR_WIDTH-PADDING, right-EYE_WIDTH-PADDING]`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_sidebar.py` (import `EYE_WIDTH`, `STAR_WIDTH`, `PADDING` from `gitfourchette.sidebar.sidebardelegate` alongside the Task 1 imports; `STAR_WIDTH` won't exist yet — the RED run fails at import, which is acceptable for Step 2 as long as Step 4's GREEN run passes):

```python
def testStarClickZoneOnBranchRows(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    branch = rw.sidebar.findNodeByRef("refs/heads/master")
    rect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(branch))
    eyeX = rect.right() - EYE_WIDTH // 2
    starX = rect.right() - EYE_WIDTH - PADDING - STAR_WIDTH // 2
    assert SidebarDelegate.getClickZone(branch, rect, eyeX) == SidebarClickZone.Hide
    assert SidebarDelegate.getClickZone(branch, rect, starX) == SidebarClickZone.Star
    assert SidebarDelegate.getClickZone(branch, rect, rect.center().x()) == SidebarClickZone.Select

    # Hideable-but-not-starrable rows: star band falls through to Select
    remote = rw.sidebar.findNode(lambda n: n.kind == SidebarItem.Remote and n.data == "origin")
    rrect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(remote))
    rStarX = rrect.right() - EYE_WIDTH - PADDING - STAR_WIDTH // 2
    assert SidebarDelegate.getClickZone(remote, rrect, rStarX) == SidebarClickZone.Select


def testStarButtonClickTogglesStar(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    rect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(node))
    starPos = QPoint(rect.right() - EYE_WIDTH - PADDING - STAR_WIDTH // 2, rect.center().y())
    QTest.mouseClick(rw.sidebar.viewport(), Qt.MouseButton.LeftButton, pos=starPos)
    assert "refs/heads/no-parent" in rw.sidebar.sidebarModel.repoModel.prefs.starredRefs

    # The sidebar rebuilt; unstar via the alias row's own star button
    starRoot = rw.sidebar.findNodeByKind(SidebarItem.StarredHeader)
    alias = starRoot.children[0]
    arect = rw.sidebar.visualRect(rw.sidebar.nodeToFilterIndex(alias))
    aliasStarPos = QPoint(arect.right() - EYE_WIDTH - PADDING - STAR_WIDTH // 2, arect.center().y())
    QTest.mouseClick(rw.sidebar.viewport(), Qt.MouseButton.LeftButton, pos=aliasStarPos)
    assert "refs/heads/no-parent" not in rw.sidebar.sidebarModel.repoModel.prefs.starredRefs
    assert not rw.sidebar.findNodesByKind(SidebarItem.StarredHeader)
```

(`QPoint`/`QTest`: use however the existing test modules reference them — the qt shim re-exports both; verify with `grep -n "QTest\|QPoint" test/test_sidebar.py test/util.py` and extend imports only if missing.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -x -q -k "StarClickZone or StarButtonClick"`
Expected: FAIL (ImportError on `STAR_WIDTH`, or `SidebarClickZone` has no `Star`).

- [ ] **Step 3: SVG assets**

Create `gitfourchette/assets/icons/star-outline.svg`:

```xml
<svg viewBox="0 0 16 16" fill="none" stroke="gray" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
    <path d="M 8 2.4 L 9.53 6.5 L 13.9 6.68 L 10.47 9.4 L 11.64 13.62 L 8 11.2 L 4.36 13.62 L 5.53 9.4 L 2.1 6.68 L 6.47 6.5 Z" />
</svg>
```

Create `gitfourchette/assets/icons/star-filled.svg`:

```xml
<svg viewBox="0 0 16 16" fill="none" stroke="gray" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
    <path style="fill:gray;" d="M 8 2.4 L 9.53 6.5 L 13.9 6.68 L 10.47 9.4 L 11.64 13.62 L 8 11.2 L 4.36 13.62 L 5.53 9.4 L 2.1 6.68 L 6.47 6.5 Z" />
</svg>
```

- [ ] **Step 4: Model + delegate + view changes**

`sidebarmodel.py` — after the `HideableItems` list (~:124):

```python
    StarrableItems = sorted([
        SidebarItem.LocalBranch,
        SidebarItem.RemoteBranch,
    ])
```

After `canBeHidden` (~:182):

```python
    def canBeStarred(self):
        return self.kind in SidebarLayout.StarrableItems
```

`sidebardelegate.py` — constant next to `EYE_WIDTH` (~:26):

```python
STAR_WIDTH = 16
```

Enum member (~:33):

```python
    Star = 4
```

`getClickZone` — insert AFTER the Hide check, before the final `else` (builds on Task 1's version):

```python
        elif node.canBeStarred() and x > rect.right() - EYE_WIDTH - STAR_WIDTH - PADDING:
            return SidebarClickZone.Star
```

`paint()` — directly after the `makeRoomForEye` block (~:86-90):

```python
        isStarred = False
        makeRoomForStar = False
        if node.canBeStarred():
            isStarred = node.data in sidebarModel.repoModel.prefs.starredRefs
            makeRoomForStar = isStarred or mouseOver
```

`textRect` preparation (~:160-162) gains one more shrink:

```python
        textRect = QRect(option.rect)
        if makeRoomForEye:
            textRect.adjust(0, 0, -EYE_WIDTH, 0)
        if makeRoomForStar:
            textRect.adjust(0, 0, -STAR_WIDTH, 0)
```

(Leave the ahead/behind gating condition — `if makeRoomForEye:` — untouched: starred rows must keep their indicators; they right-align into the already-shrunk `textRect`, left of the star.)

Replace the eye-drawing block (~:225-239) with right-aligned collapsing bands — star first (leftmost), then eye; the eye's icon-choice logic is IDENTICAL to today, only its left edge changes:

```python
        # Draw star/eye buttons: bands fill right-to-left from the text edge,
        # star left of eye; each collapses when unused.
        bandLeft = textRect.right()
        if makeRoomForStar:
            r = QRect(option.rect)
            r.setLeft(bandLeft)
            r.setWidth(STAR_WIDTH)
            starIcon = stockIcon("star-filled" if isStarred else "star-outline")
            starIcon.paint(painter, r, mode=iconMode)
            bandLeft += STAR_WIDTH
        if makeRoomForEye:
            r = QRect(option.rect)
            r.setLeft(bandLeft)
            r.setWidth(EYE_WIDTH)
            if isExplicitlyShown or mouseOver and isHideAllButThisMode:
                eyeIconName = "view-exclusive"
            elif isExplicitlyHidden or (isImplicitlyHidden and isHideAllButThisMode):
                eyeIconName = "view-hidden"
            elif isImplicitlyHidden:
                eyeIconName = "view-hidden-indirect"
            else:
                eyeIconName = "view-visible"
            unpluggedIcon = stockIcon(eyeIconName)
            unpluggedIcon.paint(painter, r, mode=iconMode)
```

`sidebar.py` `mouseReleaseEvent` — add before the `warnings.warn` fallthrough (~:875):

```python
        elif zone == SidebarClickZone.Star:
            self.wantToggleStarNode(node)
            event.accept()
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -x -q -k "StarClickZone or StarButtonClick"`
Expected: PASS. (Trap: if the click test's second toggle misses, re-read the note that the sidebar REBUILDS after the first click — indexes must be re-queried, as the test already does.)

- [ ] **Step 6: Sidebar suite regression**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add gitfourchette/assets/icons/star-filled.svg gitfourchette/assets/icons/star-outline.svg \
        gitfourchette/sidebar/sidebarmodel.py gitfourchette/sidebar/sidebardelegate.py \
        gitfourchette/sidebar/sidebar.py test/test_sidebar.py
git commit -m "feat: inline star/unstar button on sidebar branch rows

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Pin Starred-alias bold behavior + full-suite verification

**Files:**
- Test: `test/test_sidebar.py` (extend `testStarBranch` only — no product code)

**Interfaces:**
- Consumes: `testStarBranch`'s existing locals `starRoot`, `folderAliasIndex`, and the `masterAlias = next(...)` line (~:824).
- Produces: regression pin for bold + `git-head` icon on the checked-out branch's alias.

- [ ] **Step 1: Add the assertions (this is a pin, not TDD — the behavior already works; the point is that it can never silently regress)**

In `testStarBranch`, locate:

```python
    masterAlias = next(c for c in starRoot.children if c.data == "refs/heads/master")
```

Insert directly AFTER that line (before the `makeNodeMenu`/unstar lines):

```python
    # Pin: the checked-out branch's alias inherits bold + HEAD icon ('master'
    # is checked out in the canned repo); other aliases stay non-bold.
    masterAliasIndex = rw.sidebar.nodeToFilterIndex(masterAlias)
    boldFont = masterAliasIndex.data(Qt.ItemDataRole.FontRole)
    assert boldFont is not None and boldFont.bold()
    assert masterAliasIndex.data(SidebarModel.Role.IconKey) == "git-head"
    folderFont = folderAliasIndex.data(Qt.ItemDataRole.FontRole)
    assert folderFont is None or not folderFont.bold()
```

(`SidebarModel` import: check the test file's imports from `gitfourchette.sidebar.sidebarmodel` and extend that line only if `SidebarModel` is missing.)

- [ ] **Step 2: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test/test_sidebar.py::testStarBranch -x -q`
Expected: PASS immediately. Sanity-check the pin bites: temporarily change `"git-head"` to `"git-headX"`, re-run, confirm FAIL, revert.

- [ ] **Step 3: Full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest test -q -n auto`
Expected: 0 failed (baseline 988 passed / 16 skipped, plus this plan's 3 new tests = expected 991 passed / 16 skipped).

- [ ] **Step 4: Commit**

```bash
git add test/test_sidebar.py
git commit -m "test: pin bold + HEAD icon on starred alias of checked-out branch

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Manual smoke (deferred to user)**

Note for the session log: check star button hover feel and slide-on-hover behavior, star rendering in both themes (recolor engine), empty-section arrow removal incl. a never-fetched remote. Do not block on it.
