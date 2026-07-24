# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging

from gitfourchette.gitdriver import argsIf
from gitfourchette.localization import *
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects, TaskPrereqs
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

REBASE_STATES = (
    RepositoryState.REBASE,
    RepositoryState.REBASE_INTERACTIVE,
    RepositoryState.REBASE_MERGE,
)

GIT_NO_EDITOR = {"GIT_EDITOR": "true"}


class RebaseOnto(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, onto: Oid | str):
        repo = self.repo

        if repo.state() != RepositoryState.NONE:
            raise AbortTask(_("Conclude the ongoing operation before rebasing."))

        # Resolve target (sidebar passes a refname, graph passes an Oid)
        if isinstance(onto, str):
            assert onto.startswith("refs/")
            reference = repo.references[onto]
            ontoId = reference.target
            ontoDisplay = reference.shorthand
            assert isinstance(ontoId, Oid)
        else:
            ontoId = onto
            ontoDisplay = shortHash(onto)

        if repo.head_is_detached:
            branchName = shortHash(repo.head_commit_id)
        else:
            branchName = repo.head_branch_shorthand

        headId = repo.head_commit_id
        ahead, _behind = repo.ahead_behind(headId, ontoId)
        if ahead == 0:
            raise AbortTask(
                _("There’s nothing to rebase: {0} has no commits of its own "
                  "beyond {1}.", bquo(branchName), bquo(ontoDisplay)),
                icon="information")

        autostashCheckbox = QCheckBox(_("Autostash (stash uncommitted changes, then reapply them)"))
        autostashCheckbox.setChecked(True)
        text = paragraphs(
            _("Do you want to rebase {0} onto {1}?", bquo(branchName), bquo(ontoDisplay)),
            _n("{n} commit will be replayed.", "{n} commits will be replayed.", n=ahead))
        yield from self.flowConfirm(text=text, verb=_("Rebase"), checkbox=autostashCheckbox)
        autostash = autostashCheckbox.isChecked()

        yield from _flowRebaseGit(
            self,
            "rebase", *argsIf(autostash, "--autostash"), str(ontoId),
            successStatus=_("Rebased {0} onto {1}.", tquo(branchName), tquo(ontoDisplay)))


def _flowRebaseGit(task: RepoTask, *args: str, successStatus: str):
    """Run a git rebase command and resolve its outcome. Shared by every
    rebase task; call with `yield from`. A nonzero exit is only an error if
    the repo did NOT end up in (or remain in) a rebase state — otherwise the
    rebase merely paused on conflicts and the banner takes over."""
    task.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
    driver = yield from task.flowCallGit(*args, env=dict(GIT_NO_EDITOR), autoFail=False)

    yield from task.flowEnterWorkerThread()
    task.repo.refresh_index()
    stillRebasing = task.repo.state() in REBASE_STATES
    yield from task.flowEnterUiThread()

    if driver.exitCode() != 0 and not stillRebasing:
        raise AbortTask(driver.htmlErrorText())
    if stillRebasing:
        task.epilog.status = _("Rebase interrupted: resolve conflicts, then continue the rebase.")
        task.epilog.jumpTo = NavLocator.inWorkdir()
    else:
        task.epilog.status = successStatus
