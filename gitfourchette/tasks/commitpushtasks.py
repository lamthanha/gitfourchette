# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""
Fork: Commit-and-Push — Fork.dev-style Shift+Commit.

Runs NewCommit (cancelling its dialog aborts everything), then pushes the
checked-out branch to its upstream QUIETLY (status-bar indicator only, like
quiet fetch). If the branch has no upstream, falls back to the Push dialog.
"""

from gitfourchette.localization import *
from gitfourchette.porcelain import *
from gitfourchette.tasks.committasks import NewCommit
from gitfourchette.tasks.nettasks import PushBranch
from gitfourchette.tasks.repotask import RepoTask, TaskEffects, TaskPrereqs
from gitfourchette.toolbox import *


class CommitAndPush(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoDetached

    def broadcastProcesses(self) -> bool:
        # Fork-style quiet push: no modal ProcessDialog.
        return False

    def flow(self):
        yield from self.flowSubtask(NewCommit, buttonCaption=_("Co&mmit and Push"))

        branchName = self.repo.head_branch_shorthand
        branch = self.repo.branches.local[branchName]
        upstream = branch.upstream
        if upstream is None:
            # No upstream to push to quietly: let the user pick one.
            yield from self.flowSubtask(PushBranch, branchName)
            return

        remoteName, remoteBranchName = split_remote_branch_shorthand(upstream.shorthand)
        self.epilog.effects |= TaskEffects.Refs
        yield from self.flowCallGit(
            "push",
            "--porcelain",
            "--progress",
            "--",
            remoteName,
            f"refs/heads/{branchName}:refs/heads/{remoteBranchName}")
        self.epilog.status = _("Pushed {0} to {1}.", tquo(branchName), tquo(upstream.shorthand))
