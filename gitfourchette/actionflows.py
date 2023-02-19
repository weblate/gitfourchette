from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.util import messageSummary, shortHash, stockIcon, asyncMessageBox, showWarning, setWindowModal
from gitfourchette.widgets.pushdialog import PushDialog
from html import escape
import pygit2


class ActionFlows(QObject):
    pullBranch = Signal(str, str)  # local branch, remote ref to pull
    pushComplete = Signal()

    def __init__(self, repo: pygit2.Repository, parent: QWidget):
        super().__init__(parent)
        self.repo = repo
        self.parentWidget = parent

    def pushFlow(self, branchName: str = None):
        if not branchName:
            branchName = porcelain.getActiveBranchShorthand(self.repo)

        try:
            branch = self.repo.branches.local[branchName]
        except KeyError:
            showWarning(self.parentWidget, self.tr("No branch to push"),
                        self.tr("To push, you must be on a local branch. Try switching to a local branch first."))
            return

        dlg = PushDialog(self.repo, branch, self.parentWidget)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.accepted.connect(self.pushComplete)
        dlg.show()
        return dlg

    def pullFlow(self, branchName: str = None):
        if not branchName:
            branchName = porcelain.getActiveBranchShorthand(self.repo)

        try:
            branch = self.repo.branches.local[branchName]
        except KeyError:
            showWarning(self.parentWidget, self.tr("No branch to pull"),
                        self.tr("To pull, you must be on a local branch. Try switching to a local branch first."))
            return

        bu: pygit2.Branch = branch.upstream
        if not bu:
            showWarning(self.parentWidget, self.tr("No remote-tracking branch"),
                        self.tr("Can’t pull because “{0}” isn’t tracking a remote branch.").format(escape(branch.shorthand)))
            return

        self.pullBranch.emit(branch.branch_name, bu.shorthand)
