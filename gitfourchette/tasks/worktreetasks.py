# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — Phase 3: worktree management tasks.
# Mutations run the real git binary (flowCallGit); pygit2 stays read-only.
# -----------------------------------------------------------------------------

from gitfourchette.forms.newworktreedialog import NewWorktreeDialog
from gitfourchette.localization import *
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects
from gitfourchette.toolbox import *


class NewWorktree(RepoTask):
    def flow(self, branchName: str = ""):
        dlg = NewWorktreeDialog(self.repo, branchName, self.parentWidget())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()

        path = dlg.path()
        if dlg.wantNewBranch():
            args = ["worktree", "add", "-b", dlg.newBranchName(), path, dlg.baseRef()]
        else:
            args = ["worktree", "add", path, dlg.existingBranch()]

        driver = yield from self.flowCallGit(*args, autoFail=False)
        if driver.exitCode() != 0:
            raise AbortTask(driver.htmlErrorText())

        self.epilog.effects |= TaskEffects.Refs

        openOffer = yield from self.flowConfirmOpenNewWorktree(path)
        if openOffer:
            self.rw.openRepo.emit(path, NavLocator())

    def flowConfirmOpenNewWorktree(self, path: str):
        try:
            yield from self.flowConfirm(
                title=_("Worktree created"),
                text=_("Worktree created at {0}.", bquo(compactPath(path)))
                     + "<br>" + _("Open it in a new tab?"),
                verb=_("Open"),
                cancelText=_("Not Now"))
            return True
        except AbortTask:
            return False
