# -----------------------------------------------------------------------------
# Fork: tests for Shift-modifier staging buttons and the CommitAndPush task.
# -----------------------------------------------------------------------------

from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.pushdialog import PushDialog
from gitfourchette.tasks import CommitAndPush, NewCommit

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


def testShiftSwapsStagingButtonLabels(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/hello.txt", "hello")
    rw = mainWindow.openRepo(wd)
    area = rw.diffArea

    assert area.stageButton.text() == "Stage"
    assert area.unstageButton.text() == "Unstage"
    assert area.commitButton.text() == "Commit"

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    assert area.stageButton.text() == "Stage All"
    assert area.unstageButton.text() == "Unstage All"
    assert area.commitButton.text() == "Commit and Push"
    # All-variants enable off the LIST, not the selection
    assert area.stageButton.isEnabled()

    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)
    assert area.stageButton.text() == "Stage"
    assert area.commitButton.text() == "Commit"


def testShiftStageAllAndUnstageAll(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/apple.txt", "a")
    writeFile(f"{wd}/banana.txt", "b")
    writeFile(f"{wd}/cherry.txt", "c")
    rw = mainWindow.openRepo(wd)
    area = rw.diffArea

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    area.stageButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)
    assert {"apple.txt", "banana.txt", "cherry.txt"} <= set(qlvGetRowData(rw.stagedFiles))
    assert qlvGetRowData(rw.dirtyFiles) == []

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    area.unstageButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)
    assert qlvGetRowData(rw.stagedFiles) == []
    assert {"apple.txt", "banana.txt", "cherry.txt"} <= set(qlvGetRowData(rw.dirtyFiles))


def testShiftStageAllScopedToActiveFilter(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/apple.txt", "a")
    writeFile(f"{wd}/banana.txt", "b")
    rw = mainWindow.openRepo(wd)
    area = rw.diffArea

    rw.dirtyFiles.searchBar.popUp()
    QTest.keyClicks(rw.dirtyFiles.searchBar.lineEdit, "banana")
    assert qlvGetRowData(rw.dirtyFiles) == ["banana.txt"]

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    area.stageButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)

    assert qlvGetRowData(rw.stagedFiles) == ["banana.txt"]  # only the visible file
    QTest.keyPress(rw.dirtyFiles.searchBar.lineEdit, Qt.Key.Key_Escape)
    assert "apple.txt" in qlvGetRowData(rw.dirtyFiles)  # apple stayed unstaged


def testShiftCommitButtonRunsCommitAndPush(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    writeFile(f"{wd}/pushme.txt", "via the button")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    QTest.keyPress(mainWindow, Qt.Key.Key_Shift)
    rw.diffArea.commitButton.click()
    QTest.keyRelease(mainWindow, Qt.Key.Key_Shift)

    dialog: CommitDialog = findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "pushed from the button")
    dialog.acceptButton.click()

    localTip = rw.repo.branches.local["master"].target
    assert rw.repo.branches.remote["localfs/master"].target == localTip


def testCommitAndPushDialogCaption(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    writeFile(f"{wd}/pushme.txt", "and push me now")
    rw = mainWindow.openRepo(wd)
    _stageFirstDirtyFile(rw)

    CommitAndPush.invoke(rw)
    dialog: CommitDialog = findQDialog(rw, "commit")
    assert dialog.acceptButton.text() == "Co&mmit and Push"
    assert dialog.windowTitle() == "Commit and Push"
    dialog.reject()

    # Plain commit dialog is unaffected
    NewCommit.invoke(rw)
    dialog2: CommitDialog = findQDialog(rw, "commit")
    assert dialog2.acceptButton.text() == "Co&mmit"
    assert dialog2.windowTitle() != "Commit and Push"
    dialog2.reject()
