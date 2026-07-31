# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — Phase 3: worktree management tasks.
# Mutations run the real git binary (flowCallGit); pygit2 stays read-only.
# -----------------------------------------------------------------------------

import os
from pathlib import Path

from gitfourchette import settings
from gitfourchette.forms.newworktreedialog import NewWorktreeDialog
from gitfourchette.forms.textinputdialog import TextInputDialog
from gitfourchette.localization import *
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects
from gitfourchette.toolbox import *


class NewWorktree(RepoTask):
    def flow(self, prefillRef: str = ""):
        dlg = NewWorktreeDialog(self.repo, prefillRef, self.parentWidget())
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

        # Fork-style quiet flow: refresh this tab's sidebar with the new
        # worktree row *before* switching away. self.rw.openRepo.emit() below
        # switches tabs synchronously (hiding this RepoWidget), and a hidden
        # RepoWidget's task runner won't apply queued epilog effects (see
        # RepoWidget.onTaskRunnerReady) -- so RefreshRepo must run as an
        # explicit subtask here rather than via self.epilog.effects.
        from gitfourchette.tasks import RefreshRepo
        yield from self.flowSubtask(RefreshRepo, TaskEffects.Refs)

        # Open the new worktree's tab directly -- no "open it?" confirmation.
        self.rw.openRepo.emit(path, NavLocator())


class MoveWorktree(RepoTask):
    def flow(self, path: str):
        mainInfo = next((wt for wt in self.repoModel.worktrees if wt.isMain), None)
        if mainInfo is not None and os.path.realpath(path) == os.path.realpath(mainInfo.path):
            raise AbortTask(_("You can’t move the main worktree."), icon="information")

        from gitfourchette.application import GFApplication
        mainWindow = GFApplication.instance().mainWindow
        if mainWindow is not None and mainWindow.tabWidgetForWorkdirPath(path) is not None:
            raise AbortTask(
                _("This worktree is open in a tab. Close its tab before moving it."),
                icon="information")

        def validate(candidate: str) -> str:
            candidate = candidate.strip()
            if not candidate:
                return _("Enter a path for the worktree.")
            try:
                if os.path.realpath(candidate) == os.path.realpath(path):
                    return _("This is already the worktree’s current location.")
                if Path(candidate).is_file():
                    return _("There’s already a file at this path.")
                if Path(candidate).is_dir() and any(Path(candidate).iterdir()):
                    return _("This directory exists and is not empty.")
            except OSError:
                return _("This path can’t be checked.")
            return ""

        dlg = TextInputDialog(
            self.parentWidget(),
            _("Move worktree"),
            "",
            subtitle=_("Move worktree {0} to:", bquo(os.path.basename(os.path.normpath(path)))),
            multilineSubtitle=True)
        dlg.setText(path)
        dlg.setValidator(validate)
        yield from self.flowDialog(dlg)
        newPath = dlg.lineEdit.text().strip()
        dlg.deleteLater()

        driver = yield from self.flowCallGit("worktree", "move", path, newPath, autoFail=False)
        if driver.exitCode() != 0:
            raise AbortTask(driver.htmlErrorText())

        # Migrate path-keyed state that was recorded under the worktree's old
        # location: tab color override (keyed by realpath) and history entry
        # -- nickname, etc. (keyed by normpath).
        oldTabColorKey = os.path.realpath(path)
        tabColor = settings.prefs.tabColorOverrides.pop(oldTabColorKey, None)
        if tabColor is not None:
            settings.prefs.tabColorOverrides[os.path.realpath(newPath)] = tabColor
            settings.prefs.setDirty()
            settings.prefs.write()

        oldHistoryEntry = settings.history.repos.pop(os.path.normpath(path), None)
        if oldHistoryEntry is not None:
            newHistoryEntry = settings.history.getRepo(newPath)
            seq = newHistoryEntry.get('seq', oldHistoryEntry.get('seq'))
            newHistoryEntry.update(oldHistoryEntry)
            if seq is not None:
                newHistoryEntry['seq'] = seq
            settings.history.setDirty()

        self.epilog.effects |= TaskEffects.Refs


class RemoveWorktree(RepoTask):
    def flow(self, path: str):
        mainInfo = next((wt for wt in self.repoModel.worktrees if wt.isMain), None)
        if mainInfo is not None and os.path.realpath(path) == os.path.realpath(mainInfo.path):
            raise AbortTask(_("You can’t remove the main worktree."), icon="information")

        from gitfourchette.application import GFApplication
        mainWindow = GFApplication.instance().mainWindow
        if mainWindow is not None and mainWindow.tabWidgetForWorkdirPath(path) is not None:
            raise AbortTask(
                _("This worktree is open in a tab. Close its tab before removing it."),
                icon="information")

        yield from self.flowConfirm(
            text=_("Really remove worktree {0}?", bquo(compactPath(path)))
                 + "<br>" + _("Its files will be deleted from disk."),
            verb=_("Remove Worktree"))

        driver = yield from self.flowCallGit("worktree", "remove", path, autoFail=False)
        if driver.exitCode() != 0:
            yield from self.flowConfirm(
                text=paragraphs(
                    _("Git refused to remove this worktree "
                      "(it may contain uncommitted changes, or it may be locked)."),
                    driver.htmlErrorText(),
                    _("Force-remove it?"),
                ),
                verb=_("Force Remove"))
            driver = yield from self.flowCallGit("worktree", "remove", "--force", path, autoFail=False)
            if driver.exitCode() != 0:
                raise AbortTask(driver.htmlErrorText())

        self.epilog.effects |= TaskEffects.Refs


class PruneWorktrees(RepoTask):
    def flow(self):
        driver = yield from self.flowCallGit("worktree", "prune", autoFail=False)
        if driver.exitCode() != 0:
            raise AbortTask(driver.htmlErrorText())
        self.epilog.effects |= TaskEffects.Refs
