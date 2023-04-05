from gitfourchette.graphview.commitlogmodel import CommitLogModel
from gitfourchette.qt import *
from gitfourchette.toolbox import *
import pygit2


class CommitLogFilter(QSortFilterProxyModel):
    hiddenOids: set[pygit2.Oid]

    def __init__(self, parent):
        super().__init__(parent)
        self.hiddenOids = set()
        self.setDynamicSortFilter(True)

    @property
    def clModel(self) -> CommitLogModel:
        return self.sourceModel()

    def setHiddenCommits(self, hiddenCommits: set[pygit2.Oid]):
        self.hiddenOids = hiddenCommits

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        if sourceRow == 0:  # Uncommitted Changes
            return True

        commit = self.clModel._commitSequence[sourceRow - 1]  # -1 to account for Uncommited Changes
        return commit.oid not in self.hiddenOids


