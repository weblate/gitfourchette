from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *


DEFAULT_MODE = "mixed"


MODE_LABELS = {
    "soft": "&Soft",
    "mixed": "&Mixed",
    "hard": "&Hard",
}


MODE_TEXT = {
    "soft":
        """
        <ul>
        <li><p><b>Unstaged files</b>:<br>don’t touch</p>
        <li><p><b>Staged files</b>:<br>don’t touch</p>
        <li><p><b>Commits since {commit}</b>:<br>move contents of those commits to Staged</p>
        </ul>
        """,
        # <p>Does not touch the index file (staging area) or the working tree at all
        # (but resets the <b>HEAD</b> to <b>{commit}</b>, just like all modes do).
        # This leaves all your changed files
        # “Changes to be committed”, as <code>git status</code> would put it.</p>

    "mixed":
        """
        <ul>
        <li><p><b>Unstaged files</b>:<br>don’t touch</p>
        <li><p><b>Staged files</b>:<br>move to Unstaged</p>
        <li><p><b>Commits since {commit}</b>:<br>move contents of those commits to Unstaged</p>
        </ul>
        """,
        # <p>Resets the index but not the working tree (i.e., the changed files are preserved but
        # not marked for commit) and reports what has not been updated.</p>

    "hard":
        """
        <ul>
        <li><p><b>Unstaged files</b>:<br>⚠ <em>nuke changes</em> to files that have been touched by any commits since {commit}</p>
        <li><p><b>Staged files</b>:<br>⚠ <em>nuke all changes</em></p>
        <li><p><b>Commits since {commit}</b>:<br>⚠ <em>nuke all changes</em>, effectively nuking the branch’s history since {commit}</p>
        </ul>
        """,
        # <p>Resets the index and working tree. Any changes to tracked files in the working tree
        # since <b>{commit}</b> are discarded.</p>

    "recurse":
        """
        <p><b>Recurse Submodules</b> will also recursively reset the working tree of all active
        submodules according to the commit recorded in the superproject, also
        setting the submodules’ <b>HEAD</b> to be detached at that commit.</p>
        """
}


class ResetHeadDialog(QDialog):
    oid: Oid
    activeMode: str
    recurseSubmodules: bool
    helpLabel: QLabel
    recurseCheckbox: QCheckBox

    def setHelp(self):
        title = self.activeMode.title()
        text = MODE_TEXT[self.activeMode].format(commit=self.shortsha)

        if self.recurseCheckbox.isEnabled() and self.recurseCheckbox.isChecked():
            title += " --recurse-submodules"
            text += MODE_TEXT['recurse']

        self.helpLabel.setText(F"<p><big>{title}</big></p>{text}")

    def setRecurse(self, checked: bool):
        self.recurseSubmodules = checked
        self.setHelp()

    def setActiveMode(self, mode: str, checked: bool = True):
        if not checked:
            return
        self.activeMode = mode
        self.recurseCheckbox.setEnabled(mode not in ['soft', 'mixed'])
        self.setHelp()

    def __init__(self, oid: Oid, parent: QWidget):
        super().__init__(parent)

        self.activeMode = "???"
        self.recurseSubmodules = False
        self.shortsha = shortHash(oid)

        self.setWindowTitle(F"Reset HEAD to {shortHash(oid)}")

        self.recurseCheckbox = QCheckBox("&Recurse\nSubmodules")
        self.recurseCheckbox.toggled.connect(self.setRecurse)

        self.helpLabel = QLabel()
        self.helpLabel.setWordWrap(True)
        self.helpLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.helpLabel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        vbar = QFrame()
        vbar.setFrameShape(QFrame.Shape.VLine)
        vbar.setFrameShadow(QFrame.Shadow.Sunken)

        mainVBL = QVBoxLayout()
        centerHBL = QHBoxLayout()
        buttonVBL = QVBoxLayout()

        self.modeButtons = {}
        for mode in ['soft', 'mixed', 'hard']:
            button = QRadioButton(MODE_LABELS[mode])
            button.toggled.connect(lambda checked, mode=mode: self.setActiveMode(mode, checked))
            buttonVBL.addWidget(button)
            self.modeButtons[mode] = button

        #buttonVBL.addSpacing(16)
        #buttonVBL.addWidget(self.recurseCheckbox)
        buttonVBL.addStretch()

        centerHBL.addLayout(buttonVBL)
        centerHBL.addSpacing(16)
        centerHBL.addWidget(vbar)
        centerHBL.addSpacing(8)
        centerHBL.addWidget(self.helpLabel)

        mainVBL.addWidget(QLabel(
            F"Pick the <b>reset mode</b> to use for resetting <b>HEAD</b> to <b>{self.shortsha}</b>:"))
        mainVBL.addSpacing(16)
        mainVBL.addLayout(centerHBL)
        mainVBL.addSpacing(16)
        mainVBL.addWidget(buttonBox)

        self.resize(500, 400)
        self.setLayout(mainVBL)

        self.modeButtons[DEFAULT_MODE].setChecked(True)
        self.modeButtons[DEFAULT_MODE].setFocus()

        self.setModal(True)
