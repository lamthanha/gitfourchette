# -----------------------------------------------------------------------------
# Fork: tests for Shift-modifier staging buttons and the CommitAndPush task.
# -----------------------------------------------------------------------------

from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.pushdialog import PushDialog
from gitfourchette.tasks import CommitAndPush

from .util import *


def _stageFirstDirtyFile(rw):
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)


def testCommitAndPushQuietToUpstream(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)  # retargets upstreams to localfs/*
    writeFile(f"{wd}/pushme.txt", "and push me now")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    oldRemoteTip = rw.repo.branches.remote["localfs/master"].target

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "commit-and-push me")
    dialog.acceptButton.click()

    localTip = rw.repo.branches.local["master"].target
    assert localTip != oldRemoteTip
    assert rw.repo.branches.remote["localfs/master"].target == localTip


def testCommitAndPushNoUpstreamFallsBackToPushDialog(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    runShellScript("git switch -c standalone", wd)  # branch with no upstream
    writeFile(f"{wd}/pushme.txt", "no upstream here")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "commit on standalone")
    dialog.acceptButton.click()

    pushDialog = findQDialog(rw, "push.+branch")
    assert isinstance(pushDialog, PushDialog)
    pushDialog.reject()


def testCommitAndPushCancelledCommitPushesNothing(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    writeFile(f"{wd}/pushme.txt", "never committed")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    oldLocalTip = rw.repo.branches.local["master"].target
    oldRemoteTip = rw.repo.branches.remote["localfs/master"].target

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    dialog.reject()

    assert rw.repo.branches.local["master"].target == oldLocalTip
    assert rw.repo.branches.remote["localfs/master"].target == oldRemoteTip
