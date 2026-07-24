# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging
import shlex
import shutil
import tempfile
from pathlib import Path

from gitfourchette.forms.rebasetododialog import RebaseTodoDialog, SquashMessageDialog
from gitfourchette.gitdriver import argsIf
from gitfourchette.localization import *
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.rebasetodo import (
    RebaseTodoRow,
    combinedSquashMessage,
    formatTodoFile,
    planEditorMessages,
    validateTodo,
)
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

        # Fork-style flow: a clean worktree rebases immediately; only prompt
        # (with the autostash option) when there's something to stash.
        yield from self.flowEnterWorkerThread()
        repo.refresh_index()
        dirty = bool(repo.status(untracked_files="no"))
        yield from self.flowEnterUiThread()

        autostash = False
        if dirty:
            autostashCheckbox = QCheckBox(_("Autostash (stash uncommitted changes, then reapply them)"))
            autostashCheckbox.setChecked(True)
            text = paragraphs(
                _("Do you want to rebase {0} onto {1}?", bquo(branchName), bquo(ontoDisplay)),
                _n("{n} commit will be replayed.", "{n} commits will be replayed.", n=ahead),
                _("You have uncommitted changes."))
            yield from self.flowConfirm(text=text, verb=_("Rebase"), checkbox=autostashCheckbox)
            autostash = autostashCheckbox.isChecked()

        yield from _flowRebaseGit(
            self,
            "rebase", *argsIf(autostash, "--autostash"), str(ontoId),
            successStatus=_("Rebased {0} onto {1}.", tquo(branchName), tquo(ontoDisplay)),
            upToDateStatus=_("{0} is already up to date with {1}.", tquo(branchName), tquo(ontoDisplay)))


def _writeRebaseScripts(payloadDir: str, todoText: str, editorMessages: list[str]) -> tuple[str, str]:
    """Write the todo file, the queued editor messages, and two tiny shell
    scripts into payloadDir. Returns (sequenceEditorPath, messageEditorPath).

    The sequence editor overwrites git's generated todo with ours. The message
    editor pops msg-N.txt on git's Nth editor invocation (reword/squash
    prompts); when no payload file exists for an invocation, it leaves the file
    untouched so git's default message applies (graceful degradation, e.g.
    after a conflict pause when ContinueRebase runs with GIT_EDITOR=true)."""
    payload = Path(payloadDir)
    (payload / "todo.txt").write_text(todoText, "utf-8")
    for i, message in enumerate(editorMessages, start=1):
        if message:
            if not message.endswith("\n"):
                message += "\n"
            (payload / f"msg-{i}.txt").write_text(message, "utf-8")

    quotedPayload = shlex.quote(str(payload))

    sequenceEditor = payload / "sequence-editor.sh"
    sequenceEditor.write_text(
        "#!/bin/sh\n"
        f"cat {quotedPayload}/todo.txt > \"$1\"\n",
        "utf-8")
    sequenceEditor.chmod(0o700)

    messageEditor = payload / "message-editor.sh"
    messageEditor.write_text(
        "#!/bin/sh\n"
        f"dir={quotedPayload}\n"
        "n=$(cat \"$dir/counter\" 2>/dev/null || echo 0)\n"
        "n=$((n + 1))\n"
        "printf %s \"$n\" > \"$dir/counter\"\n"
        "if [ -f \"$dir/msg-$n.txt\" ]; then\n"
        "    cat \"$dir/msg-$n.txt\" > \"$1\"\n"
        "fi\n",
        "utf-8")
    messageEditor.chmod(0o700)

    return str(sequenceEditor), str(messageEditor)


def _flowPrepareTodo(task: RepoTask, fromCommit: Oid):
    repo = task.repo

    if repo.state() != RepositoryState.NONE:
        raise AbortTask(_("Conclude the ongoing operation before rebasing."))

    headId = repo.head_commit_id
    if fromCommit != headId and not repo.descendant_of(headId, fromCommit):
        raise AbortTask(_("To edit history from this commit, it must be an "
                          "ancestor of the current HEAD."))

    startCommit = repo.peel_commit(fromCommit)
    baseId = startCommit.parent_ids[0] if startCommit.parent_ids else None

    yield from task.flowEnterWorkerThread()
    rows = []
    flattenedMerges = 0
    walker = repo.walk(headId, SortMode.TOPOLOGICAL)
    if baseId is not None:
        walker.hide(baseId)
    for commit in walker:
        if len(commit.parent_ids) > 1:
            # git rebase -i omits merges from the todo (default flattening)
            flattenedMerges += 1
            continue
        rows.append(RebaseTodoRow(
            oid=str(commit.id),
            summary=messageSummary(commit.message)[0],
            author=commit.author.name,
            fullMessage=commit.message))
    repo.refresh_index()
    dirty = bool(repo.status(untracked_files="no"))
    yield from task.flowEnterUiThread()

    if not rows:
        raise AbortTask(_("There are no commits to edit in this range."),
                        icon="information")

    return rows, baseId, flattenedMerges, dirty, headId


def _flowExecuteTodo(task: RepoTask, execRows: list[RebaseTodoRow], baseId: Oid | None,
                      headId: Oid, autostash: bool, successStatus: str):
    repo = task.repo

    if repo.state() != RepositoryState.NONE or repo.head_commit_id != headId:
        raise AbortTask(_("The repository changed while the dialog was open. "
                          "Start the interactive rebase again."))

    todoError = validateTodo(execRows)
    if todoError:
        raise AbortTask(todoError)

    payloadDir = tempfile.mkdtemp(prefix="gitfourchette-rebase-todo-")
    try:
        yield from task.flowEnterWorkerThread()
        sequenceEditor, messageEditor = _writeRebaseScripts(
            payloadDir, formatTodoFile(execRows), planEditorMessages(execRows))
        yield from task.flowEnterUiThread()

        env = dict(GIT_NO_EDITOR)
        env["GIT_SEQUENCE_EDITOR"] = shlex.quote(sequenceEditor)
        env["GIT_EDITOR"] = shlex.quote(messageEditor)

        targetArgs = ["--root"] if baseId is None else [str(baseId)]
        yield from _flowRebaseGit(
            task,
            "rebase", "--interactive", *argsIf(autostash, "--autostash"), *targetArgs,
            env=env,
            successStatus=successStatus)
    finally:
        shutil.rmtree(payloadDir, ignore_errors=True)

    yield from task.flowEnterWorkerThread()
    fullySucceeded = repo.state() == RepositoryState.NONE and not repo.any_conflicts
    newHead = repo.head_commit_id
    yield from task.flowEnterUiThread()

    if fullySucceeded:
        task.epilog.jumpTo = NavLocator.inCommit(newHead)


class InteractiveRebase(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, fromCommit: Oid):
        rows, baseId, flattenedMerges, dirty, headId = yield from _flowPrepareTodo(self, fromCommit)

        dlg = RebaseTodoDialog(rows, flattenedMerges, dirty, self.parentWidget())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        execRows = dlg.executionRows()
        autostash = dlg.autostash()

        yield from _flowExecuteTodo(self, execRows, baseId, headId, autostash,
                                    successStatus=_("Interactive rebase completed."))


def _mapSelectionToRows(rows: list[RebaseTodoRow], oids: tuple[Oid, ...]) -> list[int]:
    """Indices (into newest-first rows) of the selected commits. Aborts if any
    selected commit is absent from the todo (merge commit, or outside the
    range walked from the oldest selection to HEAD)."""
    rowIndexByOid = {row.oid: i for i, row in enumerate(rows)}
    try:
        return sorted(rowIndexByOid[str(oid)] for oid in oids)
    except KeyError as exc:
        raise AbortTask(_("Can’t rewrite this selection: it includes a merge commit "
                          "or a commit outside the current branch’s history.")) from exc


class SquashCommits(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, oids: tuple[Oid, ...]):
        assert len(oids) >= 2
        rows, baseId, _flattenedMerges, dirty, headId = yield from _flowPrepareTodo(self, oids[-1])

        indices = _mapSelectionToRows(rows, oids)
        if indices != list(range(indices[0], indices[-1] + 1)):
            raise AbortTask(_("Can’t squash a non-contiguous selection of commits."))

        # rows is newest-first: the LAST selected index is the oldest commit —
        # it stays "pick" and becomes the squash target; the rest fold into it.
        for i in indices[:-1]:
            rows[i].action = "squash"
        execRows = list(reversed(rows))

        prefill = combinedSquashMessage(execRows, execRows.index(rows[indices[0]]))
        dlg = SquashMessageDialog(prefill, len(indices), dirty, self.parentWidget())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        # rows[indices[0]] is the chain's last-executed squash row: its message wins
        rows[indices[0]].message = dlg.message()
        autostash = dlg.autostash()

        yield from _flowExecuteTodo(
            self, execRows, baseId, headId, autostash,
            successStatus=_("Squashed {0} commits into one.", len(indices)))


class DropCommits(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, oids: tuple[Oid, ...]):
        rows, baseId, _flattenedMerges, dirty, headId = yield from _flowPrepareTodo(self, oids[-1])

        for i in _mapSelectionToRows(rows, oids):
            rows[i].action = "drop"
        execRows = list(reversed(rows))

        todoError = validateTodo(execRows)
        if todoError:
            raise AbortTask(todoError)

        autostashCheckbox = None
        if dirty:
            autostashCheckbox = QCheckBox(_("Autostash (stash uncommitted changes, then reapply them)"))
            autostashCheckbox.setChecked(True)
        text = paragraphs(
            _n("Do you want to drop {n} commit?", "Do you want to drop {n} commits?", n=len(oids)),
            _("This rewrites the branch’s history."))
        if autostashCheckbox is not None:
            yield from self.flowConfirm(text=text, verb=_("Drop"), icon="warning",
                                        checkbox=autostashCheckbox)
        else:
            yield from self.flowConfirm(text=text, verb=_("Drop"), icon="warning")
        autostash = autostashCheckbox is not None and autostashCheckbox.isChecked()

        yield from _flowExecuteTodo(
            self, execRows, baseId, headId, autostash,
            successStatus=_n("Dropped {n} commit.", "Dropped {n} commits.", n=len(oids)))


def rebaseProgress(repo: Repo) -> tuple[int, int, str]:
    """Return (step, total, branchShorthand) for the rebase in progress.
    Zeros/empty string when unknown."""
    from pathlib import Path
    from contextlib import suppress

    for stateDir, stepFile, endFile in (
            ("rebase-merge", "msgnum", "end"),
            ("rebase-apply", "next", "last")):
        base = Path(repo.in_gitdir(stateDir, common=False))
        if not base.is_dir():
            continue

        def read(name: str) -> str:
            with suppress(OSError):
                return (base / name).read_text("utf-8").strip()
            return ""

        with suppress(ValueError):
            step = int(read(stepFile) or 0)
            total = int(read(endFile) or 0)
            headName = read("head-name")
            branch = ""
            if headName.startswith("refs/"):
                branch = RefPrefix.split(headName)[1]
            return step, total, branch
    return 0, 0, ""


class _RebaseSequencerTask(RepoTask):
    """Base class for continue/skip/abort."""

    def checkRebasing(self):
        if self.repo.state() not in REBASE_STATES:
            raise AbortTask(_("No rebase is in progress."), icon="information")


class ContinueRebase(_RebaseSequencerTask):
    def flow(self):
        self.checkRebasing()

        yield from self.flowEnterWorkerThread()
        self.repo.refresh_index()
        anyConflicts = self.repo.any_conflicts
        yield from self.flowEnterUiThread()

        if anyConflicts:
            raise AbortTask(_("Fix merge conflicts before continuing the rebase."))

        yield from _flowRebaseGit(self, "rebase", "--continue", successStatus=_("Rebase completed."))


class SkipRebase(_RebaseSequencerTask):
    def flow(self):
        self.checkRebasing()
        yield from self.flowConfirm(
            text=_("Do you want to skip the current commit and continue the rebase?"),
            verb=_("Skip"))

        yield from _flowRebaseGit(self, "rebase", "--skip", successStatus=_("Rebase completed."))


class AbortRebase(_RebaseSequencerTask):
    def flow(self):
        self.checkRebasing()
        yield from self.flowConfirm(
            text=_("Do you want to abort the rebase and return the branch to its previous state?"),
            verb=_("Abort rebase"),
            icon="warning")

        self.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
        yield from self.flowCallGit("rebase", "--abort", env=dict(GIT_NO_EDITOR))
        self.epilog.status = _("Rebase aborted.")


def _flowRebaseGit(task: RepoTask, *args: str, successStatus: str, upToDateStatus: str = "",
                   env: dict[str, str] | None = None):
    """Run a git rebase command and resolve its outcome. Shared by every
    rebase task; call with `yield from`. A nonzero exit is only an error if
    the repo did NOT end up in (or remain in) a rebase state — otherwise the
    rebase merely paused and the banner takes over."""
    task.epilog.effects |= TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir
    oldHead = task.repo.head_commit_id
    if env is None:
        env = dict(GIT_NO_EDITOR)
    driver = yield from task.flowCallGit(*args, env=env, autoFail=False)

    yield from task.flowEnterWorkerThread()
    task.repo.refresh_index()
    stillRebasing = task.repo.state() in REBASE_STATES
    anyConflicts = task.repo.any_conflicts
    yield from task.flowEnterUiThread()

    if driver.exitCode() != 0 and not stillRebasing:
        raise AbortTask(driver.htmlErrorText())
    if stillRebasing:
        if anyConflicts:
            task.epilog.status = _("Rebase interrupted: resolve conflicts, then continue the rebase.")
        else:
            task.epilog.status = _("Rebase paused. Use the banner to continue, skip, or abort.")
        task.epilog.jumpTo = NavLocator.inWorkdir()
    elif anyConflicts:
        task.epilog.status = _("Rebase succeeded, but reapplying your stashed changes caused conflicts.")
        task.epilog.jumpTo = NavLocator.inWorkdir()
    elif upToDateStatus and task.repo.head_commit_id == oldHead:
        task.epilog.status = upToDateStatus
    else:
        task.epilog.status = successStatus
