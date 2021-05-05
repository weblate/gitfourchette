from allqt import *
from util import labelQuote
import git


class TrackedBranchDialog(QDialog):
    newTrackingBranchName: str

    def __init__(self, repo: git.Repo, localBranchName: str, parent):
        super().__init__(parent)

        self.setWindowTitle(F"Edit Tracked Branch")

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        localBranch: git.Head = repo.heads[localBranchName]

        trackingBranch: git.RemoteReference = localBranch.tracking_branch()

        comboBox = QComboBox(self)
        self.comboBox = comboBox

        def addComboBoxItem(caption, userData, isCurrent):
            if isCurrent:
                caption = "• " + caption
            comboBox.addItem(caption, userData=userData)
            if isCurrent:
                comboBox.setCurrentIndex(comboBox.count() - 1)

        self.newTrackingBranchName = None
        if trackingBranch:
            self.newTrackingBranchName = trackingBranch.name

        addComboBoxItem("<don’t track any remote branch>", userData=None, isCurrent=not trackingBranch)

        for remote in repo.remotes:
            comboBox.insertSeparator(comboBox.count())
            for ref in remote.refs:
                addComboBoxItem(ref.name, userData=ref.name, isCurrent=trackingBranch and trackingBranch.name == ref.name)

        comboBox.activated.connect(lambda x: self.onChangeNewRemoteBranchName(comboBox.itemData(x, role=Qt.UserRole)))#print(comboBox.itemData(x, role=Qt.UserRole)))

        layout = QVBoxLayout()
        if trackingBranch:
            layout.addWidget(QLabel(F"Local branch <b>{labelQuote(localBranchName)}</b> currently tracks remote branch <b>{labelQuote(trackingBranch.name)}</b>."))
        else:
            layout.addWidget(QLabel(F"Local branch <b>{labelQuote(localBranchName)}</b> currently doesn’t track any remote branch."))

        layout.addWidget(QLabel(F"Pick a new remote branch to track:"))
        layout.addWidget(comboBox)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def onChangeNewRemoteBranchName(self, remoteBranchName):
        self.newTrackingBranchName = remoteBranchName
