# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — dialog for the NewWorktree task (Phase 3).
# -----------------------------------------------------------------------------

import os
from pathlib import Path

from gitfourchette import settings
from gitfourchette.localization import *
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.worktrees import DEFAULT_WORKTREE_PATH_TEMPLATE, renderWorktreePathTemplate


class NewWorktreeDialog(QDialog):
    def __init__(self, repo: Repo, prefillRef: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("NewWorktreeDialog")
        self.setWindowTitle(_("New Worktree"))

        localBranches = sorted(repo.branches.local)
        remoteBranches = sorted(b for b in repo.branches.remote if not b.endswith("/HEAD"))

        self.pathEdit = QLineEdit(self)
        self.pathLabel = QLabel(_("&Path:"), self)
        self.pathLabel.setBuddy(self.pathEdit)
        browseButton = QPushButton(_("&Browse…"), self)
        browseButton.clicked.connect(self.browse)

        self.existingRadio = QRadioButton(_("Check out an &existing branch:"), self)
        self.existingCombo = QComboBox(self)
        self.existingCombo.addItems(localBranches)
        # existingCombo doesn't share a row with another widget, so it can't
        # starve a sibling, but cap it too for consistency (local branch
        # names are short in practice, so this is a no-op most of the time).
        self.existingCombo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.existingCombo.setMinimumContentsLength(16)

        self.newRadio = QRadioButton(_("Create a &new branch:"), self)
        self.newNameEdit = QLineEdit(self)
        self.baseRefCombo = QComboBox(self)
        self.baseRefCombo.addItems(localBranches + remoteBranches)
        # A long remote ref (e.g. "origin/feature/some-very-long-name") must
        # not balloon the combo's sizeHint and starve newNameEdit of width:
        # cap the closed-state width to a fixed content length. The popup
        # list still shows full names; only the collapsed box is capped.
        self.baseRefCombo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.baseRefCombo.setMinimumContentsLength(16)

        prefillExisting = ""
        prefillNewName = ""
        prefillNewBase = ""
        if prefillRef:
            prefix, shorthand = RefPrefix.split(prefillRef)
            if prefix == RefPrefix.REMOTES:
                _remoteName, tail = split_remote_branch_shorthand(shorthand)
                if tail in localBranches:
                    # A same-name local exists: creating it again would be a
                    # guaranteed git failure — offer the local instead.
                    prefillExisting = tail
                else:
                    prefillNewName = tail
                    prefillNewBase = shorthand
            else:
                prefillExisting = shorthand  # refs/heads/x or bare shorthand

        if prefillExisting and prefillExisting in localBranches:
            self.existingCombo.setCurrentText(prefillExisting)
        self.existingRadio.setChecked(True)
        if prefillNewName:
            self.newRadio.setChecked(True)
            self.newNameEdit.setText(prefillNewName)
            self.baseRefCombo.setCurrentText(prefillNewBase)

        # Default path: sibling of the main worktree root, named <repo>-<branch>
        mainRoot = os.path.dirname(os.path.normpath(repo.commondir)) \
            if os.path.basename(os.path.normpath(repo.commondir)) == ".git" \
            else os.path.normpath(repo.commondir)
        self._mainRoot = mainRoot
        initialBranchForPath = prefillNewName if prefillNewName else self.existingCombo.currentText()
        self.pathEdit.setText(self.defaultPathForBranch(initialBranchForPath))

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.okButton = buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        self.errorLabel = QLabel(self)
        self.errorLabel.setWordWrap(True)

        pathRow = QHBoxLayout()
        pathRow.addWidget(self.pathEdit)
        pathRow.addWidget(browseButton)

        newRow = QHBoxLayout()
        newRow.addWidget(self.newNameEdit, 1)  # give the name field the lion's share of the row
        newRow.addWidget(QLabel(_("from:"), self))
        newRow.addWidget(self.baseRefCombo)

        layout = QVBoxLayout(self)
        layout.addWidget(self.pathLabel)
        layout.addLayout(pathRow)
        layout.addSpacing(8)
        layout.addWidget(self.existingRadio)
        layout.addWidget(self.existingCombo)
        layout.addWidget(self.newRadio)
        layout.addLayout(newRow)
        layout.addWidget(self.errorLabel)
        layout.addWidget(buttonBox)

        for signalSource in (self.pathEdit.textChanged, self.newNameEdit.textChanged,
                             self.existingRadio.toggled, self.newRadio.toggled,
                             self.existingCombo.currentTextChanged):
            signalSource.connect(self._revalidate)
        self.existingCombo.currentTextChanged.connect(self._trackDefaultPath)
        self.newNameEdit.textChanged.connect(self._trackDefaultPath)
        self._userEditedPath = False
        self.pathEdit.textEdited.connect(lambda: setattr(self, "_userEditedPath", True))

        # Open-list fix: typing a new-branch name means "create a new branch";
        # picking an existing branch from the combo means the opposite.
        # textEdited/activated fire on user gestures only, so the
        # setNewBranch()/setExistingBranch() test API stays inert here.
        self.newNameEdit.textEdited.connect(self._typedNewBranchName)
        self.existingCombo.activated.connect(self._pickedExistingBranch)

        self._revalidate()
        self.setModal(True)

        # Open-list fix: widen so the path (the longest field) is readable.
        # max() so long translated labels can still widen it further.
        self.resize(max(640, self.width()), self.height())

    def defaultPathForBranch(self, branch: str) -> str:
        path = renderWorktreePathTemplate(
            settings.prefs.worktreePathTemplate, self._mainRoot, branch)
        if not path:  # blank template: fall back to the built-in default
            path = renderWorktreePathTemplate(
                DEFAULT_WORKTREE_PATH_TEMPLATE, self._mainRoot, branch)
        return path

    def _trackDefaultPath(self):
        if not self._userEditedPath:
            branch = self.newNameEdit.text() if self.wantNewBranch() else self.existingCombo.currentText()
            self.pathEdit.setText(self.defaultPathForBranch(branch))

    def _typedNewBranchName(self):
        if not self.newRadio.isChecked():
            self.newRadio.setChecked(True)  # toggled -> _revalidate
            self._trackDefaultPath()

    def _pickedExistingBranch(self, _index: int):
        if not self.existingRadio.isChecked():
            self.existingRadio.setChecked(True)
            self._trackDefaultPath()

    def _revalidate(self):
        error = ""
        p = self.pathEdit.text().strip()
        if not p:
            error = _("Enter a path for the new worktree.")
        else:
            try:
                if Path(p).is_file():
                    error = _("There’s already a file at this path.")
                elif Path(p).is_dir() and any(Path(p).iterdir()):
                    error = _("This directory exists and is not empty.")
            except OSError:
                error = _("This path can’t be checked.")
        if not error and self.wantNewBranch() and not self.newNameEdit.text().strip():
            error = _("Enter a name for the new branch.")
        if not error and not self.wantNewBranch() and not self.existingCombo.currentText():
            error = _("There’s no local branch to check out.")
        self.errorLabel.setText(error)
        self.okButton.setEnabled(not error)

    def browse(self):
        qfd = PersistentFileDialog.saveFile(
            self, "NewWorktree", _("New worktree location"), os.path.basename(self.pathEdit.text()))
        qfd.fileSelected.connect(self.pathEdit.setText)
        qfd.fileSelected.connect(lambda: setattr(self, "_userEditedPath", True))
        qfd.show()

    # --- Test/consumer API -------------------------------------------------

    def path(self) -> str:
        return self.pathEdit.text().strip()

    def wantNewBranch(self) -> bool:
        return self.newRadio.isChecked()

    def existingBranch(self) -> str:
        return self.existingCombo.currentText()

    def newBranchName(self) -> str:
        return self.newNameEdit.text().strip()

    def baseRef(self) -> str:
        return self.baseRefCombo.currentText()

    def setPath(self, p: str):
        self._userEditedPath = True
        self.pathEdit.setText(p)

    def setExistingBranch(self, shorthand: str):
        self.existingRadio.setChecked(True)
        self.existingCombo.setCurrentText(shorthand)

    def setNewBranch(self, name: str, baseRef: str):
        self.newRadio.setChecked(True)
        self.newNameEdit.setText(name)
        self.baseRefCombo.setCurrentText(baseRef)
