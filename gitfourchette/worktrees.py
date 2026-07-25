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


def listWorktrees(workdir: str) -> list[WorktreeInfo]:
    """List all worktrees of the repo containing workdir ([] on any git failure)."""
    stdout = GitDriver.runSync("worktree", "list", "--porcelain", directory=workdir)
    if not stdout:
        return []
    return parseWorktreeListPorcelain(stdout)
