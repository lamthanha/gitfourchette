# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------
# Forkette extension — dialog for the NewWorktree task (Phase 3).
# -----------------------------------------------------------------------------

import os
from pathlib import Path

from gitfourchette.localization import *
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class NewWorktreeDialog(QDialog):
    def __init__(self, repo: Repo, prefillBranch: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("NewWorktreeDialog")
        self.setWindowTitle(_("New Worktree"))

        localBranches = sorted(repo.branches.local)

        self.pathEdit = QLineEdit(self)
        browseButton = QPushButton(_("&Browse…"), self)
        browseButton.clicked.connect(self.browse)

        self.existingRadio = QRadioButton(_("Check out an &existing branch:"), self)
        self.existingCombo = QComboBox(self)
        self.existingCombo.addItems(localBranches)

        self.newRadio = QRadioButton(_("Create a &new branch:"), self)
        self.newNameEdit = QLineEdit(self)
        self.baseRefCombo = QComboBox(self)
        self.baseRefCombo.addItems(localBranches)

        if prefillBranch and prefillBranch in localBranches:
            self.existingCombo.setCurrentText(prefillBranch)
        self.existingRadio.setChecked(True)

        # Default path: sibling of the main worktree root, named <repo>-<branch>
        mainRoot = os.path.dirname(os.path.normpath(repo.commondir)) \
            if os.path.basename(os.path.normpath(repo.commondir)) == ".git" \
            else os.path.normpath(repo.commondir)
        self._mainRoot = mainRoot
        self.pathEdit.setText(self.defaultPathForBranch(self.existingCombo.currentText()))

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
        newRow.addWidget(self.newNameEdit)
        newRow.addWidget(QLabel(_("from:"), self))
        newRow.addWidget(self.baseRefCombo)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("&Path:"), self))
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
        self._revalidate()
        self.setModal(True)

    def defaultPathForBranch(self, branch: str) -> str:
        repoName = os.path.basename(self._mainRoot)
        leaf = branch.replace("/", "-") if branch else "worktree"
        return os.path.join(os.path.dirname(self._mainRoot), f"{repoName}-{leaf}")

    def _trackDefaultPath(self):
        if not self._userEditedPath:
            branch = self.newNameEdit.text() if self.wantNewBranch() else self.existingCombo.currentText()
            self.pathEdit.setText(self.defaultPathForBranch(branch))

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
