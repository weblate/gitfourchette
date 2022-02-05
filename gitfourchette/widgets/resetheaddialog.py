from gitfourchette.qt import *
from gitfourchette.util import shortHash


# TODO: document --merge and --keep, and expose them through the dialog


explainers = {
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

    "merge":
        """
        """,
        # <p>Resets the index and updates the files in the working tree that are different between
        # <b>{commit}</b> and <b>HEAD</b>, but keeps those which are different between the index and working
        # tree (i.e. which have changes which have not been added). If a file that is different
        # between <b>{commit}</b> and the index has unstaged changes, reset is aborted.</p>
        # <!--<p>In other words, <b>Merge</b> does something like a <code>git read-tree -u -m {commit}</code>,
        # but carries forward unmerged index entries.</p>-->

    "keep":
        """
        """,
        # <p>Resets index entries and updates files in the working tree that are different between
        # <b>{commit}</b> and <b>HEAD</b>. If a file that is different between <b>{commit}</b>
        # and <b>HEAD</b> has local changes, reset is aborted.</p>

    "recurse":
        """
        <p><b>Recurse Submodules</b> will also recursively reset the working tree of all active
        submodules according to the commit recorded in the superproject, also
        setting the submodules’ <b>HEAD</b> to be detached at that commit.</p>
        """
}


class ResetHeadDialog(QDialog):
    activeMode: str
    recurseSubmodules: bool
    helpLabel: QLabel
    recurseCheckbox: QCheckBox

    def setHelp(self):
        title = F"--{self.activeMode}"
        text = explainers[self.activeMode].format(commit=self.shortsha)

        if self.recurseCheckbox.isEnabled() and self.recurseCheckbox.isChecked():
            title += " --recurse-submodules"
            text += explainers['recurse']

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

    def __init__(self, hexsha: str, parent: QWidget):
        super().__init__(parent)

        self.activeMode = "???"
        self.recurseSubmodules = False
        self.shortsha = shortHash(hexsha)

        self.setWindowTitle(F"Reset HEAD to {shortHash(hexsha)}")

        softButton = QRadioButton("&Soft")
        mixedButton = QRadioButton("Mi&xed")
        hardButton = QRadioButton("&Hard")
        mergeButton = QRadioButton("Mer&ge")
        keepButton = QRadioButton("&Keep")

        self.recurseCheckbox = QCheckBox("&Recurse\nSubmodules")
        self.recurseCheckbox.toggled.connect(self.setRecurse)

        self.helpLabel = QLabel()
        self.helpLabel.setWordWrap(True)
        self.helpLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.helpLabel.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        def bindMode(button: QRadioButton, mode: str):
            button.toggled.connect(lambda checked, mode=mode: self.setActiveMode(mode, checked))

        bindMode(softButton, 'soft')
        bindMode(mixedButton, 'mixed')
        bindMode(hardButton, 'hard')
        bindMode(mergeButton, 'merge')
        bindMode(keepButton, 'keep')

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        vbar = QFrame()
        vbar.setFrameShape(QFrame.VLine)
        vbar.setFrameShadow(QFrame.Sunken)

        mainVBL = QVBoxLayout()
        centerHBL = QHBoxLayout()
        buttonVBL = QVBoxLayout()

        buttonVBL.addWidget(softButton)
        buttonVBL.addWidget(mixedButton)
        buttonVBL.addWidget(hardButton)
        #buttonVBL.addWidget(mergeButton)
        #buttonVBL.addWidget(keepButton)
        buttonVBL.addSpacing(16)
        buttonVBL.addWidget(self.recurseCheckbox)
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

        mixedButton.setChecked(True)
        mixedButton.setFocus()

        self.resize(500, 400)
        self.setLayout(mainVBL)

        self.setModal(True)
