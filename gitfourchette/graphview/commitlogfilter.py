from gitfourchette.graphview.commitlogmodel import CommitLogModel
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class CommitLogFilter(QSortFilterProxyModel):
    hiddenOids: set[Oid]

    def __init__(self, parent):
        super().__init__(parent)
        self.hiddenOids = set()
        self.setDynamicSortFilter(True)

    @property
    def clModel(self) -> CommitLogModel:
        return self.sourceModel()

    def setHiddenCommits(self, hiddenCommits: set[Oid]):
        self.hiddenOids = hiddenCommits

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        commit = self.clModel._commitSequence[sourceRow]

        return (not commit) or (commit.oid not in self.hiddenOids)


