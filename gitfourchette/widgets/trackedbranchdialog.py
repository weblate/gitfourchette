from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.widgets.brandeddialog import makeBrandedDialog
import pygit2


class TrackedBranchDialog(QDialog):
    newTrackingBranchName: str

    def __init__(self, repo: pygit2.Repository, localBranchName: str, parent):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Edit Tracked Branch"))

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        localBranch: pygit2.Branch = repo.branches.local[localBranchName]
        trackedBranch: pygit2.Branch = localBranch.upstream

        comboBox = QComboBox(self)
        comboBox.setInsertPolicy(QComboBox.NoInsert)  # Prevent QComboBox from stealing enter keypresses on Linux
        self.comboBox = comboBox

        self.newTrackedBranchName = None
        if trackedBranch:
            self.newTrackedBranchName = trackedBranch.shorthand

        addComboBoxItem(comboBox, self.tr("[don’t track any remote branch]"), userData=None, isCurrent=not trackedBranch)

        for remoteName, remoteBranches in porcelain.getRemoteBranchNames(repo).items():
            if not remoteBranches:
                continue
            comboBox.insertSeparator(comboBox.count())
            for remoteBranch in remoteBranches:
                addComboBoxItem(
                    comboBox,
                    F"{remoteName}/{remoteBranch}",
                    userData=F"{remoteName}/{remoteBranch}",
                    isCurrent=trackedBranch and trackedBranch.name == F"refs/remotes/{remoteName}/{remoteBranch}")

        comboBox.currentIndexChanged.connect(
            lambda index: self.onChangeNewRemoteBranchName(comboBox.itemData(index, role=Qt.ItemDataRole.UserRole)))

        explainer = "<p>"
        if trackedBranch:
            explainer += self.tr("Local branch <b>“{0}”</b> currently tracks remote branch <b>“{1}”</b>.")\
                .format(escape(localBranch.shorthand), escape(trackedBranch.shorthand))
        else:
            explainer += self.tr("Local branch <b>“{0}”</b> currently does <b>not</b> track a remote branch.")\
                .format(escape(localBranch.shorthand))
        explainer += "</p><p>" + self.tr("Pick a new remote branch to track:") + "</p>"
        explainerLabel = QLabel(explainer)
        explainerLabel.setWordWrap(True)
        explainerLabel.setMinimumHeight(explainerLabel.fontMetrics().height()*4)

        hintLabel = QLabel(self.tr("If you can’t find the remote branch you want, try fetching the remote first."))
        tweakWidgetFont(hintLabel, 90)

        layout = QVBoxLayout()
        layout.addWidget(explainerLabel)
        layout.addWidget(comboBox)
        layout.addWidget(hintLabel)
        layout.addWidget(buttonBox)

        makeBrandedDialog(self, layout, self.tr("Set branch tracked by “{0}”").format(escape(elide(localBranch.shorthand))))

        self.setModal(True)
        self.resize(512, 128)
        self.setMaximumHeight(self.height())

    def onChangeNewRemoteBranchName(self, remoteBranchName):
        self.newTrackedBranchName = remoteBranchName
