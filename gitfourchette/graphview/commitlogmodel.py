import enum

from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *


EPHEMERAL_ROW_CACHE = 150
""" Number of rows to keep track of for MessageElidedRole """


class SpecialRow(enum.IntEnum):
    Invalid = 0
    UncommittedChanges = enum.auto()
    Commit = enum.auto()
    TruncatedHistory = enum.auto()
    EndOfShallowHistory = enum.auto()


class CommitLogModel(QAbstractListModel):
    CommitRole: Qt.ItemDataRole = Qt.ItemDataRole.UserRole + 0
    OidRole: Qt.ItemDataRole = Qt.ItemDataRole.UserRole + 1
    MessageElidedRole: Qt.ItemDataRole = Qt.ItemDataRole.UserRole + 2
    AuthorColumnXRole: Qt.ItemDataRole = Qt.ItemDataRole.UserRole + 3
    SpecialRowRole: Qt.ItemDataRole = Qt.ItemDataRole.UserRole + 4

    # Reference to RepoState.commitSequence
    _commitSequence: list[Commit] | None
    _extraRow: SpecialRow

    _authorColumnX: int
    _elidedRows: dict[int, bool]

    def __init__(self, parent):
        super().__init__(parent)
        self._commitSequence = None
        self._extraRow = SpecialRow.Invalid
        self._authorColumnX = -1
        self._elidedRows = {}

    @property
    def isValid(self):
        return self._commitSequence is not None

    def clear(self):
        self.setCommitSequence(None)
        self._elidedRows.clear()
        self._extraRow = SpecialRow.Invalid

    def setCommitSequence(self, newCommitSequence: list[Commit] | None):
        self.beginResetModel()
        self._commitSequence = newCommitSequence
        self.endResetModel()

    def refreshTopOfCommitSequence(self, nRemovedRows, nAddedRows, newCommitSequence: list[Commit]):
        parent = QModelIndex()  # it's not a tree model so there's no parent

        self._commitSequence = newCommitSequence

        # DON'T interleave beginRemoveRows/beginInsertRows!
        # It'll crash with QSortFilterProxyModel!
        if nRemovedRows != 0:
            self.beginRemoveRows(parent, 0, nRemovedRows)
            self.endRemoveRows()

        if nAddedRows != 0:
            self.beginInsertRows(parent, 0, nAddedRows)
            self.endInsertRows()

    def rowCount(self, *args, **kwargs) -> int:
        if not self.isValid:
            return 0
        else:
            n = len(self._commitSequence)
            if self._extraRow != SpecialRow.Invalid:
                n += 1
            return n

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole):
        if not self.isValid:
            return None

        row = index.row()

        if role == Qt.ItemDataRole.DisplayRole:
            return None

        elif role == CommitLogModel.CommitRole:
            try:
                return self._commitSequence[row]
            except IndexError:
                pass

        elif role == CommitLogModel.OidRole:
            try:
                commit = self._commitSequence[row]
                if commit is not None:
                    return commit.id
            except IndexError:
                pass

        elif role == CommitLogModel.SpecialRowRole:
            if row == 0:
                return SpecialRow.UncommittedChanges
            elif row < len(self._commitSequence):
                return SpecialRow.Commit
            else:
                return self._extraRow

        elif role == Qt.ItemDataRole.ToolTipRole:
            tip = ""

            try:
                commit = self._commitSequence[row]
            except IndexError:
                return tip
            if commit is None:
                return tip

            isCommitMessageElided = index.row() in self._elidedRows

            if self._authorColumnX <= 0:  # author hidden in narrow window
                if isCommitMessageElided:
                    tip += commitMessageTooltip(commit)
                tip += commitAuthorTooltip(commit)
            else:
                x = self.parent().mapFromGlobal(QCursor.pos()).x()
                if x >= self._authorColumnX:
                    tip = commitAuthorTooltip(commit)
                elif isCommitMessageElided:
                    tip = commitMessageTooltip(commit)

            return tip

    def setData(self, index, value, role=None):
        if role == CommitLogModel.AuthorColumnXRole:
            self._authorColumnX = value
            return True

        elif role == CommitLogModel.MessageElidedRole:
            row = index.row()
            self._elidedRows.pop(row, False)

            if value:
                # Since we just popped this row, re-setting it will bump it to the end of the keys
                # (dicts keep key insertion order in Python 3.7+)
                self._elidedRows[row] = True

                # Nuke old entries if the dict grew beyond the threshold
                if len(self._elidedRows) > EPHEMERAL_ROW_CACHE * 2:
                    keep = list(self._elidedRows.keys())[-EPHEMERAL_ROW_CACHE:]
                    self._elidedRows = {k: True for k in keep}

            return True

        return False


def commitAuthorTooltip(commit: Commit) -> str:
    def formatTime(sig: Signature):
        qdt = QDateTime.fromSecsSinceEpoch(sig.time, Qt.TimeSpec.OffsetFromUTC, sig.offset * 60)
        s = QLocale().toString(qdt, QLocale.FormatType.LongFormat)
        return escape(s)

    def formatPerson(sig: Signature):
        return f"<b>{escape(sig.name)}</b> &lt;{escape(sig.email)}&gt;"

    author = commit.author
    committer = commit.committer

    markup = "<p style='white-space: pre'>"
    markup += formatPerson(author)

    if author == committer:
        markup += f"<small><br>{formatTime(author)}"
    elif author.name == committer.name and author.email == committer.email:
        suffixA = translate("CommitTooltip", "(authored)")
        suffixC = translate("CommitTooltip", "(committed)")
        markup += (f"<small><br>{formatTime(author)} {suffixA}"
                   f"<br>{formatTime(committer)} *{suffixC}")
    else:
        committedBy = translate("CommitTooltip", "Committed by {0}")
        markup += (f"<small><br>{formatTime(author)}<br><br>"
                   + "*" + committedBy.format(formatPerson(committer)) +
                   f"<br><small>{formatTime(committer)}")

    return markup


def commitMessageTooltip(commit: Commit) -> str:
    message = commit.message.rstrip()
    maxLength = max(len(line) for line in message.splitlines())
    message = escape(message)

    if maxLength <= 80:
        # Keep Qt from wrapping tooltip text when the message is made up of short lines
        return "<p style='white-space: pre'>" + message
    else:
        return "<p>" + message.replace('\n', '<br>')
