# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.graphview.commitlogmodel import CommitLogModel
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class CommitLogFilter(QSortFilterProxyModel):
    hiddenIds: set[Oid]

    def __init__(self, parent):
        super().__init__(parent)
        self.hiddenIds = set()
        self.setDynamicSortFilter(True)

    @property
    def clModel(self) -> CommitLogModel:
        return self.sourceModel()

    @benchmark
    def setHiddenCommits(self, hiddenIds: set[Oid]):
        # Invalidating the filter can be costly, so avoid if possible
        if self.hiddenIds == hiddenIds:
            return
        # Duplicate the set so we don't prematurely bail from above
        # if hidden commits change in the same set object
        self.hiddenIds = set(hiddenIds)
        self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        try:
            commit = self.clModel._commitSequence[sourceRow]
            return (not commit) or (commit.id not in self.hiddenIds)
        except IndexError:
            # Probably an extra special row
            return True
