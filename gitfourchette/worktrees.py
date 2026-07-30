# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — not part of upstream GitFourchette.
# Worktree enumeration via `git worktree list --porcelain` (reads only;
# worktree mutations live in gitfourchette/tasks/worktreetasks.py).
# -----------------------------------------------------------------------------

import dataclasses
import os

from gitfourchette.gitdriver import GitDriver


@dataclasses.dataclass(frozen=True)
class WorktreeInfo:
    path: str
    head: str = ""
    branch: str = ""
    "Full refname of the checked-out branch; empty when detached or bare."
    isMain: bool = False
    isBare: bool = False
    isDetached: bool = False
    locked: bool = False
    lockedReason: str = ""
    prunable: bool = False
    prunableReason: str = ""


def parseWorktreeListPorcelain(text: str) -> list[WorktreeInfo]:
    """Parse `git worktree list --porcelain` output (blank-line-separated records).
    The first record is always the main worktree (or the bare repo itself)."""
    infos = []
    records = [r for r in text.strip().split("\n\n") if r.strip()]
    for i, record in enumerate(records):
        fields: dict = {"isMain": i == 0}
        for line in record.splitlines():
            key, _sep, value = line.partition(" ")
            if key == "worktree":
                fields["path"] = value
            elif key == "HEAD":
                fields["head"] = value
            elif key == "branch":
                fields["branch"] = value
            elif key == "bare":
                fields["isBare"] = True
            elif key == "detached":
                fields["isDetached"] = True
            elif key == "locked":
                fields["locked"] = True
                fields["lockedReason"] = value
            elif key == "prunable":
                fields["prunable"] = True
                fields["prunableReason"] = value
            # Unknown keys from future git versions are ignored.
        if fields.get("path"):
            infos.append(WorktreeInfo(**fields))
    return infos


def worktreeName(wt: WorktreeInfo) -> str:
    """Display name for a worktree: the basename of its path.
    Shared by the sidebar (list rows, branch-menu "Open in ... Worktree"
    actions) and SwitchBranch's worktree-aware "already checked out" dialog."""
    return os.path.basename(os.path.normpath(wt.path))


def listWorktrees(workdir: str) -> list[WorktreeInfo]:
    """List all worktrees of the repo containing workdir ([] on any git failure).

    Blocking (uncapped synchronous subprocess wait) — never call on the UI
    thread. UI paths run `worktree list --porcelain` via RepoTask.flowCallGit
    and feed the output to parseWorktreeListPorcelain/updateWorktrees.
    """
    stdout = GitDriver.runSync("worktree", "list", "--porcelain", directory=workdir)
    if not stdout:
        return []
    return parseWorktreeListPorcelain(stdout)


DEFAULT_WORKTREE_PATH_TEMPLATE = "$BASE_ROOT/$REPO_NAME-$BRANCH"


def renderWorktreePathTemplate(template: str, mainRoot: str, branch: str) -> str:
    """Expand $BASE_PATH / $BASE_ROOT / $REPO_NAME / $BRANCH in a worktree
    path template (vocabulary borrowed from VS Code's Git-worktree-manager).
    Unknown $VARS are left literal. Returns "" for a blank template."""
    if not template.strip():
        return ""
    mainRoot = os.path.normpath(mainRoot)
    leaf = branch.replace("/", "-") if branch else "worktree"
    for var, value in (
            ("$BASE_PATH", mainRoot),
            ("$BASE_ROOT", os.path.dirname(mainRoot)),
            ("$REPO_NAME", os.path.basename(mainRoot)),
            ("$BRANCH", leaf),
    ):
        template = template.replace(var, value)
    return os.path.normpath(template)
