# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""Widget-level tests for RebaseTodoDialog, constructed directly (no repo).
The mainWindow fixture is only used to bootstrap the QApplication."""

import re

import pytest

from gitfourchette.forms.rebasetododialog import RebaseTodoDialog
from gitfourchette.rebasetodo import RebaseTodoRow, planEditorMessages
from .util import *


def _rows():
    # Display order: newest first ("three" is HEAD)
    return [
        RebaseTodoRow(oid="c" * 40, summary="ir: three", author="Alice",
                      fullMessage="ir: three\n\nbody three\n"),
        RebaseTodoRow(oid="b" * 40, summary="ir: two", author="Bob",
                      fullMessage="ir: two\n"),
        RebaseTodoRow(oid="a" * 40, summary="ir: one", author="Alice",
                      fullMessage="ir: one\n"),
    ]


def _dialog(mainWindow, rows=None, flattenedMerges=0, offerAutostash=False, hasBase=True):
    dlg = RebaseTodoDialog(rows or _rows(), flattenedMerges, offerAutostash, hasBase, None)
    return dlg


def testTodoDialogDefaults(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    assert re.search(r"interactive rebase", dlg.windowTitle(), re.I)
    assert [r.summary for r in dlg.rows()] == ["ir: three", "ir: two", "ir: one"]
    assert [r.summary for r in dlg.executionRows()] == ["ir: one", "ir: two", "ir: three"]
    assert all(r.action == "pick" for r in dlg.rows())
    assert dlg.okButton.isEnabled()
    assert not dlg.errorLabel.isVisibleTo(dlg)
    assert not dlg.mergeWarningLabel.isVisibleTo(dlg)
    assert not dlg.autostashCheckBox.isVisibleTo(dlg)
    assert not dlg.autostash()
    dlg.deleteLater()


def testTodoDialogValidationGatesOkButton(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    # Display index 2 == oldest == first executed: cannot be squashed
    dlg.setAction(2, "squash")
    assert not dlg.okButton.isEnabled()
    assert dlg.errorLabel.isVisibleTo(dlg)
    dlg.setAction(2, "pick")
    assert dlg.okButton.isEnabled()
    assert not dlg.errorLabel.isVisibleTo(dlg)
    dlg.deleteLater()


def testTodoDialogAllDroppedIsAllowed(tempDir, mainWindow):
    # Dropping every commit resets the branch to the base -- a real operation
    dlg = _dialog(mainWindow)
    for i in range(3):
        dlg.setAction(i, "drop")
    assert dlg.okButton.isEnabled()
    assert not dlg.errorLabel.isVisibleTo(dlg)
    dlg.deleteLater()


def testTodoDialogAllDroppedDisablesOkWithoutBase(tempDir, mainWindow):
    # Rebasing from the root commit: dropping everything leaves nothing behind
    dlg = _dialog(mainWindow, hasBase=False)
    for i in range(3):
        dlg.setAction(i, "drop")
    assert not dlg.okButton.isEnabled()
    assert dlg.errorLabel.isVisibleTo(dlg)
    dlg.setAction(0, "pick")
    assert dlg.okButton.isEnabled()
    assert not dlg.errorLabel.isVisibleTo(dlg)
    dlg.deleteLater()


def testTodoDialogMoveRow(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.moveRow(0, 1)  # "three" below "two"
    assert [r.summary for r in dlg.rows()] == ["ir: two", "ir: three", "ir: one"]
    assert [r.summary for r in dlg.executionRows()] == ["ir: one", "ir: three", "ir: two"]
    dlg.deleteLater()


def testTodoDialogRewordPrefillsMessage(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.setAction(1, "reword")
    assert dlg.rows()[1].message == "ir: two\n"
    dlg.table.setCurrentItem(dlg.table.topLevelItem(1))
    assert dlg.messageEdit.isEnabled()
    assert dlg.messageEdit.toPlainText() == "ir: two\n"
    dlg.setMessage(1, "ir: two, reworded")
    assert dlg.rows()[1].message == "ir: two, reworded"
    dlg.deleteLater()


def testTodoDialogSquashPrefillsCombinedMessage(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.setAction(1, "squash")  # "two" folds into "one"
    dlg.table.setCurrentItem(dlg.table.topLevelItem(1))
    assert dlg.messageEdit.isEnabled()
    preview = dlg.messageEdit.toPlainText()
    assert "ir: one" in preview
    assert "ir: two" in preview
    dlg.setMessage(1, "one and two combined")
    assert planEditorMessages(dlg.executionRows()) == ["one and two combined"]
    dlg.deleteLater()


def testTodoDialogMessageEditorDisabledForPick(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))
    assert not dlg.messageEdit.isEnabled()
    dlg.deleteLater()


def testTodoDialogMultiSelectSetAction(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    dlg.table.topLevelItem(0).setSelected(True)
    dlg.table.topLevelItem(1).setSelected(True)
    dlg.setActionForSelection("drop")
    assert [r.action for r in dlg.rows()] == ["drop", "drop", "pick"]
    assert dlg.okButton.isEnabled()  # one pick left, and it needs no fold target
    dlg.deleteLater()


def testTodoDialogAutostashCheckbox(tempDir, mainWindow):
    dlg = _dialog(mainWindow, offerAutostash=True)
    assert dlg.autostashCheckBox.isVisibleTo(dlg)
    assert dlg.autostash()
    dlg.autostashCheckBox.setChecked(False)
    assert not dlg.autostash()
    dlg.deleteLater()


def testTodoDialogMergeWarning(tempDir, mainWindow):
    dlg = _dialog(mainWindow, flattenedMerges=2)
    assert dlg.mergeWarningLabel.isVisibleTo(dlg)
    dlg.deleteLater()


def testTodoDialogRejectsOutOfRangeIndices(tempDir, mainWindow):
    dlg = _dialog(mainWindow)
    for call in (lambda: dlg.setAction(5, "drop"),
                 lambda: dlg.setMessage(5, "x"),
                 lambda: dlg.moveRow(0, 5)):
        with pytest.raises(AssertionError):
            call()
    dlg.deleteLater()
