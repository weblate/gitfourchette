from gitfourchette.qt import *
from html import escape
import pygit2


class CommitLogModel(QAbstractListModel):
    CommitRole: Qt.ItemDataRole = Qt.ItemDataRole.UserRole + 0

    _commitSequence: list[pygit2.Commit] | None

    def __init__(self, parent):
        super().__init__(parent)
        self._commitSequence = None

    @property
    def isValid(self):
        return self._commitSequence is not None

    def clear(self):
        self.setCommitSequence(None)

    def setCommitSequence(self, newCommitSequence: list[pygit2.Commit] | None):
        self.beginResetModel()
        self._commitSequence = newCommitSequence
        self.endResetModel()

    def refreshTopOfCommitSequence(self, nRemovedRows, nAddedRows, newCommitSequence: list[pygit2.Commit]):
        parent = QModelIndex()  # it's not a tree model so there's no parent

        self._commitSequence = newCommitSequence

        # DON'T interleave beginRemoveRows/beginInsertRows!
        # It'll crash with QSortFilterProxyModel!
        if nRemovedRows != 0:
            self.beginRemoveRows(parent, 1, nRemovedRows)
            self.endRemoveRows()

        if nAddedRows != 0:
            self.beginInsertRows(parent, 1, nAddedRows)
            self.endInsertRows()

    def rowCount(self, *args, **kwargs) -> int:
        if not self.isValid:
            return 0
        else:
            return 1 + len(self._commitSequence)

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole):
        if not self.isValid:
            return None

        if index.row() == 0:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return None
        elif role == CommitLogModel.CommitRole:
            return self._commitSequence[index.row() - 1]
        else:
            return None
