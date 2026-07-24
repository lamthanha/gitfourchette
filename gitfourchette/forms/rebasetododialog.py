# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.rebasetodo import (
    TODO_ACTIONS,
    RebaseTodoRow,
    combinedSquashMessage,
    validateTodo,
)
from gitfourchette.toolbox import *

_ROW_ROLE = Qt.ItemDataRole.UserRole


class _ActionDelegate(QStyledItemDelegate):
    """Combo-box editor for the Action column; other columns aren't editable."""

    def createEditor(self, parent, option, index):
        if index.column() != 0:
            return None
        combo = QComboBox(parent)
        combo.addItems(list(TODO_ACTIONS))
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentText(index.data() or "pick")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText())


class _TodoTable(QTreeWidget):
    """Flat tree widget: InternalMove drag-and-drop moves whole rows without
    destroying the items (QTableWidget can't do this cleanly)."""

    def __init__(self, dialog: "RebaseTodoDialog"):
        super().__init__(dialog)
        self._dialog = dialog

    def dropEvent(self, event):
        super().dropEvent(event)
        self._dialog._refreshMessageEditor()
        self._dialog._revalidate()


class RebaseTodoDialog(QDialog):
    def __init__(self, rowsNewestFirst: list[RebaseTodoRow], flattenedMerges: int,
                 offerAutostash: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("RebaseTodoDialog")
        self.setWindowTitle(_("Interactive Rebase"))
        self.setModal(True)
        self._offerAutostash = offerAutostash

        self.hintLabel = QLabel(
            _("Commits are listed newest first, like the graph. "
              "Git replays them bottom-up: the bottom row executes first."), self)
        self.hintLabel.setWordWrap(True)

        self.mergeWarningLabel = QLabel(
            _n("This range contains {n} merge commit. Git flattens merges during "
               "an interactive rebase: the merge itself disappears and the merged "
               "commits are replayed in a straight line.",
               "This range contains {n} merge commits. Git flattens merges during "
               "an interactive rebase: the merges themselves disappear and the merged "
               "commits are replayed in a straight line.",
               n=flattenedMerges), self)
        self.mergeWarningLabel.setWordWrap(True)
        self.mergeWarningLabel.setVisible(flattenedMerges > 0)

        self.table = _TodoTable(self)
        self.table.setColumnCount(4)
        self.table.setHeaderLabels([_("Action"), _("Commit"), _("Summary"), _("Author")])
        self.table.setRootIsDecorated(False)
        self.table.setAllColumnsShowFocus(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setItemDelegate(_ActionDelegate(self.table))
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._onContextMenu)
        self.table.itemChanged.connect(self._onItemChanged)
        self.table.currentItemChanged.connect(lambda *_a: self._refreshMessageEditor())

        for row in rowsNewestFirst:
            self._makeItem(row)
        header = self.table.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.moveUpButton = QPushButton(_("Move &Up"), self)
        self.moveUpButton.clicked.connect(lambda: self._moveCurrent(-1))
        self.moveDownButton = QPushButton(_("Move &Down"), self)
        self.moveDownButton.clicked.connect(lambda: self._moveCurrent(+1))

        self.messageEdit = QPlainTextEdit(self)
        self.messageEdit.setPlaceholderText(
            _("Select a reworded or squashed row to edit its message."))
        self.messageEdit.setEnabled(False)
        self.messageEdit.textChanged.connect(self._onMessageEdited)

        self.autostashCheckBox = QCheckBox(
            _("Autostash (stash uncommitted changes, then reapply them)"), self)
        self.autostashCheckBox.setChecked(True)
        self.autostashCheckBox.setVisible(offerAutostash)

        self.errorLabel = QLabel(self)
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setVisible(False)

        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.okButton = self.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.okButton.setText(_("&Start Rebase"))

        moveButtons = QHBoxLayout()
        moveButtons.addWidget(self.moveUpButton)
        moveButtons.addWidget(self.moveDownButton)
        moveButtons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.hintLabel)
        layout.addWidget(self.mergeWarningLabel)
        layout.addWidget(self.table, stretch=3)
        layout.addLayout(moveButtons)
        layout.addWidget(QLabel(_("Message (for reword and squash):"), self))
        layout.addWidget(self.messageEdit, stretch=1)
        layout.addWidget(self.autostashCheckBox)
        layout.addWidget(self.errorLabel)
        layout.addWidget(self.buttonBox)
        self.resize(640, 480)

        if self.table.topLevelItemCount():
            self.table.setCurrentItem(self.table.topLevelItem(0))
        self._refreshMessageEditor()
        self._revalidate()

    # ------------------------------------------------------------------------
    # Item plumbing

    def _makeItem(self, row: RebaseTodoRow):
        item = QTreeWidgetItem([row.action, row.oid[:7], row.summary, row.author])
        item.setData(0, _ROW_ROLE, row)
        # NOT ItemIsDropEnabled: forbids dropping ONTO a row (which would nest it)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsDragEnabled)
        self.table.addTopLevelItem(item)

    def _onItemChanged(self, item: QTreeWidgetItem, column: int):
        if column != 0:
            return
        row = item.data(0, _ROW_ROLE)
        action = item.text(0)
        if action not in TODO_ACTIONS:  # reject bogus edits
            with QSignalBlocker(self.table):
                item.setText(0, row.action)
            return
        self._applyAction(row, item, action)

    def _applyAction(self, row: RebaseTodoRow, item: QTreeWidgetItem, action: str):
        row.action = action
        if action == "reword" and not row.message:
            row.message = row.fullMessage
        with QSignalBlocker(self.table):
            item.setText(0, action)
        self._refreshMessageEditor()
        self._revalidate()

    def _onContextMenu(self, point):
        menu = QMenu(self.table)
        for action in TODO_ACTIONS:
            menu.addAction(action, lambda a=action: self.setActionForSelection(a))
        menu.exec(self.table.viewport().mapToGlobal(point))
        menu.deleteLater()

    def _moveCurrent(self, delta: int):
        item = self.table.currentItem()
        if item is None:
            return
        i = self.table.indexOfTopLevelItem(item)
        j = i + delta
        if 0 <= j < self.table.topLevelItemCount():
            self.moveRow(i, j)

    def _refreshMessageEditor(self):
        item = self.table.currentItem()
        row = item.data(0, _ROW_ROLE) if item is not None else None
        editable = row is not None and row.action in ("reword", "squash")
        self.messageEdit.setEnabled(editable)
        with QSignalBlocker(self.messageEdit):
            if not editable:
                self.messageEdit.setPlainText("")
            elif row.message:
                self.messageEdit.setPlainText(row.message)
            elif row.action == "squash":
                execRows = self.executionRows()
                self.messageEdit.setPlainText(
                    combinedSquashMessage(execRows, execRows.index(row)))
            else:
                self.messageEdit.setPlainText(row.fullMessage)

    def _onMessageEdited(self):
        item = self.table.currentItem()
        if item is None or not self.messageEdit.isEnabled():
            return
        row = item.data(0, _ROW_ROLE)
        row.message = self.messageEdit.toPlainText()
        self._revalidate()

    def _revalidate(self):
        error = validateTodo(self.executionRows())
        self.errorLabel.setText(error)
        self.errorLabel.setVisible(bool(error))
        self.okButton.setEnabled(not error)

    # ------------------------------------------------------------------------
    # Public API (used by InteractiveRebase and by tests)

    def rows(self) -> list[RebaseTodoRow]:
        return [self.table.topLevelItem(i).data(0, _ROW_ROLE)
                for i in range(self.table.topLevelItemCount())]

    def executionRows(self) -> list[RebaseTodoRow]:
        return list(reversed(self.rows()))

    def setAction(self, index: int, action: str):
        assert action in TODO_ACTIONS
        item = self.table.topLevelItem(index)
        assert item is not None, f"row index out of range: {index}"
        self._applyAction(item.data(0, _ROW_ROLE), item, action)

    def setMessage(self, index: int, message: str):
        item = self.table.topLevelItem(index)
        assert item is not None, f"row index out of range: {index}"
        row = item.data(0, _ROW_ROLE)
        assert row.action in ("reword", "squash")
        row.message = message
        self._refreshMessageEditor()
        self._revalidate()

    def setActionForSelection(self, action: str):
        assert action in TODO_ACTIONS
        for item in self.table.selectedItems():
            self._applyAction(item.data(0, _ROW_ROLE), item, action)

    def moveRow(self, fromIndex: int, toIndex: int):
        assert (0 <= fromIndex < self.table.topLevelItemCount()
                and 0 <= toIndex < self.table.topLevelItemCount()), \
            f"row index out of range: {fromIndex}->{toIndex}"
        item = self.table.takeTopLevelItem(fromIndex)
        self.table.insertTopLevelItem(toIndex, item)
        self.table.setCurrentItem(item)
        self._refreshMessageEditor()
        self._revalidate()

    def autostash(self) -> bool:
        return self._offerAutostash and self.autostashCheckBox.isChecked()


class SquashMessageDialog(QDialog):
    """Fork-style immediate squash: just the combined message and an optional
    autostash checkbox — the todo itself is preset by SquashCommits."""

    def __init__(self, prefillMessage: str, commitCount: int, offerAutostash: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("SquashMessageDialog")
        self.setWindowTitle(_("Squash {0} Commits", commitCount))
        self.setModal(True)
        self._offerAutostash = offerAutostash

        promptLabel = QLabel(_("Commit message for the squashed commit:"), self)

        self.messageEdit = QPlainTextEdit(self)
        self.messageEdit.setPlainText(prefillMessage)
        self.messageEdit.textChanged.connect(self._revalidate)

        self.autostashCheckBox = QCheckBox(
            _("Autostash (stash uncommitted changes, then reapply them)"), self)
        self.autostashCheckBox.setChecked(True)
        self.autostashCheckBox.setVisible(offerAutostash)

        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.okButton = self.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.okButton.setText(_("&Squash"))

        layout = QVBoxLayout(self)
        layout.addWidget(promptLabel)
        layout.addWidget(self.messageEdit)
        layout.addWidget(self.autostashCheckBox)
        layout.addWidget(self.buttonBox)
        self.resize(540, 320)
        self._revalidate()

    def _revalidate(self):
        self.okButton.setEnabled(bool(self.messageEdit.toPlainText().strip()))

    def message(self) -> str:
        return self.messageEdit.toPlainText()

    def autostash(self) -> bool:
        return self._offerAutostash and self.autostashCheckBox.isChecked()
