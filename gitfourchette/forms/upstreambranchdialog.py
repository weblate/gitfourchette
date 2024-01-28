from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import makeBrandedDialog


class UpstreamBranchDialog(QDialog):
    newUpstreamBranchName: str

    def __init__(self, repo: Repo, localBranchName: str, parent):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Edit Upstream Branch"))

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        localBranch: Branch = repo.branches.local[localBranchName]
        upstreamBranch: Branch = localBranch.upstream

        comboBox = QComboBox(self)
        comboBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # Prevent QComboBox from stealing enter keypresses on Linux
        self.comboBox = comboBox

        self.newUpstreamBranchName = ""
        if upstreamBranch:
            self.newUpstreamBranchName = upstreamBranch.shorthand

        addComboBoxItem(comboBox, self.tr("[don’t track any remote branch]"), userData=None, isCurrent=not upstreamBranch)

        for remoteName, remoteBranches in repo.listall_remote_branches().items():
            if not remoteBranches:
                continue
            comboBox.insertSeparator(comboBox.count())
            for remoteBranch in remoteBranches:
                addComboBoxItem(
                    comboBox,
                    F"{remoteName}/{remoteBranch}",
                    userData=F"{remoteName}/{remoteBranch}",
                    isCurrent=upstreamBranch and upstreamBranch.name == F"refs/remotes/{remoteName}/{remoteBranch}")

        comboBox.currentIndexChanged.connect(
            lambda index: self.onChangeUpstream(comboBox.itemData(index, role=Qt.ItemDataRole.UserRole)))

        explainer = "<p>"
        if upstreamBranch:
            explainer += self.tr("Local branch {0} currently tracks remote branch {1}."
                                 ).format(bquo(localBranch.shorthand), bquo(upstreamBranch.shorthand))
        else:
            explainer += self.tr("Local branch {0} currently does <b>not</b> track a remote branch."
                                 ).format(bquo(localBranch.shorthand))
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

        makeBrandedDialog(self, layout, self.tr("Set upstream branch of {0}").format(hquoe(localBranch.shorthand)))

        self.setModal(True)
        self.resize(512, 128)
        self.setMaximumHeight(self.height())

    def onChangeUpstream(self, remoteBranchName):
        self.newUpstreamBranchName = remoteBranchName
