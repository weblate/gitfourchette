from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.util import messageSummary, shortHash, stockIcon, asyncMessageBox, showWarning, setWindowModal
from gitfourchette.widgets.pushdialog import PushDialog
from html import escape
import pygit2


class ActionFlows(QObject):
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
