from contextlib import suppress
import logging
import os
from dataclasses import dataclass
from typing import Any

from gitfourchette import settings
from gitfourchette.porcelain import *
from gitfourchette.nav import NavContext
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables

logger = logging.getLogger(__name__)

PATCH_ROLE = Qt.ItemDataRole.UserRole + 0
FILEPATH_ROLE = Qt.ItemDataRole.UserRole + 1


def deltaModeText(delta: DiffDelta):
    om = delta.old_file.mode
    nm = delta.new_file.mode

    if om != 0 and nm != 0 and om != nm:
        # Mode change
        if nm == FileMode.BLOB_EXECUTABLE:
            return "+x"
        elif om == FileMode.BLOB_EXECUTABLE:
            return "-x"
        elif nm != FileMode.BLOB:
            return TrTables.shortFileModes(nm)
        else:
            return ""
    elif om == 0:
        # New file
        return TrTables.shortFileModes(nm)


def fileTooltip(repo: Repo, delta: DiffDelta, navContext: NavContext, isCounterpart: bool = False):
    if not delta:
        return ""

    locale = QLocale()
    of: DiffFile = delta.old_file
    nf: DiffFile = delta.new_file

    sc = delta.status_char()
    if delta.status == DeltaStatus.CONFLICTED:  # libgit2 should arguably return "U" (unmerged) for conflicts, but it doesn't
        sc = "U"

    text = "<table style='white-space: pre'>"

    def newLine(heading, caption):
        return f"<tr><td style='color:{mutedToolTipColorHex()}; text-align: right;'>{heading} </td><td>{caption}</td>"

    if sc == 'R':
        text += newLine(translate("FileList", "old name:"), escape(of.path))
        text += newLine(translate("FileList", "new name:"), escape(nf.path))
    else:
        text += newLine(translate("FileList", "name:"), escape(nf.path))

    # Status caption
    statusCaption = TrTables.diffStatusChar(sc)
    if sc not in '?U':  # show status char except for untracked and conflict
        statusCaption += f" ({sc})"
    if sc == 'U':  # conflict sides
        dc = repo.wrap_conflict(nf.path)
        if dc.deleted_by_us:
            postfix = translate("git", "deleted by us")
        elif dc.deleted_by_them:
            postfix = translate("git", "deleted by them")
        elif dc.deleted_by_both:
            postfix = translate("git", "deleted by both sides")
        elif dc.added_by_both:
            postfix = translate("git", "added by both sides")
        else:
            postfix = translate("git", "modified by both sides")
        statusCaption += f" ({postfix})"
    text += newLine(translate("FileList", "status:"), statusCaption)

    # Similarity + Old name
    if sc == 'R':
        text += newLine(translate("FileList", "similarity:"), f"{delta.similarity}%")

    # File Mode
    if sc not in 'DU':
        legend = translate("FileList", "file mode:")
        if sc in 'A?':
            text += newLine(legend, TrTables.fileMode(nf.mode))
        elif of.mode != nf.mode:
            text += newLine(legend, f"{TrTables.fileMode(of.mode)} &rarr; {TrTables.fileMode(nf.mode)}")

    # Size (if available)
    if sc not in 'DU' and nf.size != 0 and (nf.mode & FileMode.BLOB == FileMode.BLOB):
        text += newLine(translate("FileList", "size:"), locale.formattedDataSize(nf.size, 1))

    # Modified time
    if navContext.isWorkdir() and sc not in 'DU':
        with suppress(IOError):
            fullPath = os.path.join(repo.workdir, nf.path)
            fileStat = os.stat(fullPath)
            timeQdt = QDateTime.fromSecsSinceEpoch(int(fileStat.st_mtime))
            timeText = locale.toString(timeQdt, settings.prefs.shortTimeFormat)
            text += newLine(translate("FileList", "modified:"), timeText)

    # Blob IDs (DEVDEBUG only)
    if settings.DEVDEBUG:
        nChars = settings.prefs.shortHashChars
        oldBlobId = shortHash(of.id) if of.flags & DiffFlag.VALID_ID else "?" * nChars
        newBlobId = shortHash(nf.id) if nf.flags & DiffFlag.VALID_ID else "?" * nChars
        text += newLine(translate("FileList", "blob id:"), f"{oldBlobId} &rarr; {newBlobId}")

    if isCounterpart:
        if navContext == NavContext.UNSTAGED:
            counterpartText = translate("FileList", "Currently viewing diff of staged changes "
                                                    "in this file; it also has <u>unstaged</u> changes.")
        else:
            counterpartText = translate("FileList", "Currently viewing diff of unstaged changes "
                                                    "in this file; it also has <u>staged</u> changes.")
        text += f"<p>{counterpartText}</p>"

    return text


class FileListModel(QAbstractListModel):
    @dataclass
    class Entry:
        delta: DiffDelta
        diff: Diff
        patchNo: int

    entries: list[Entry]
    fileRows: dict[str, int]
    highlightedCounterpartRow: int
    navContext: NavContext

    def __init__(self, parent: QWidget, navContext: NavContext):
        super().__init__(parent)
        self.navContext = navContext
        self.clear()

    @property
    def skipConflicts(self) -> bool:
        # Hide conflicts from staged file list
        return self.navContext == NavContext.STAGED

    @property
    def repo(self) -> Repo:
        return self.parent().repo

    def clear(self):
        self.entries = []
        self.fileRows = {}
        self.highlightedCounterpartRow = -1
        self.modelReset.emit()

    def setDiffs(self, diffs: list[Diff]):
        self.beginResetModel()

        self.entries.clear()
        self.fileRows.clear()

        for diff in diffs:
            for patchNo, delta in enumerate(diff.deltas):
                if self.skipConflicts and delta.status == DeltaStatus.CONFLICTED:
                    continue
                self.fileRows[delta.new_file.path] = len(self.entries)
                self.entries.append(FileListModel.Entry(delta, diff, patchNo))

        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.entries)

    def getPatchAt(self, index: QModelIndex) -> Patch:
        row = index.row()
        entry = self.entries[row]
        try:
            patch: Patch = entry.diff[entry.patchNo]
            return patch
        except GitError as e:
            logger.warning(f"GitError when attempting to get patch: {type(e).__name__}", exc_info=True)
            return None
        except OSError as e:
            # We might get here if the UI attempts to update itself while a long async
            # operation is ongoing. (e.g. a file is being recreated)
            logger.warning(f"UI attempting to update during async operation? {type(e).__name__}", exc_info=True)
            return None

    def getDeltaAt(self, index: QModelIndex) -> DiffDelta:
        return self.entries[index.row()].delta

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == PATCH_ROLE:
            return self.getPatchAt(index)

        elif role == FILEPATH_ROLE:
            delta = self.getDeltaAt(index)
            if not delta:
                return ""

            path: str = self.getDeltaAt(index).new_file.path
            return path

        elif role == Qt.ItemDataRole.DisplayRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return "<NO DELTA>"

            path: str = self.getDeltaAt(index).new_file.path

            path = abbreviatePath(path, settings.prefs.pathDisplayStyle)

            # Show important mode info in brackets
            modeInfo = deltaModeText(delta)
            if modeInfo:
                path = f"[{modeInfo}] {path}"

            return path

        elif role == Qt.ItemDataRole.DecorationRole:
            delta = self.getDeltaAt(index)
            if not delta:
                iconName = "status_x"
            elif delta.status == DeltaStatus.UNTRACKED:
                iconName = "status_a"
            elif delta.status == DeltaStatus.CONFLICTED:
                iconName = "status_u"
            else:
                iconName = "status_" + delta.status_char().lower()
            return stockIcon(iconName)

        elif role == Qt.ItemDataRole.ToolTipRole:
            delta = self.getDeltaAt(index)
            isCounterpart = index.row() == self.highlightedCounterpartRow
            return fileTooltip(self.repo, delta, self.navContext, isCounterpart)

        elif role == Qt.ItemDataRole.SizeHintRole:
            parentWidget: QWidget = self.parent()
            return QSize(-1, parentWidget.fontMetrics().height())

        elif role == Qt.ItemDataRole.FontRole:
            if index.row() == self.highlightedCounterpartRow:
                f: QFont = self.parent().font()
                f.setUnderline(True)
                return f

        return None

    def getRowForFile(self, path: str) -> int:
        """
        Get the row number for the given path.
        Raise KeyError if the path is absent from this model.
        """
        return self.fileRows[path]

    def getFileAtRow(self, row: int) -> str:
        """
        Get the path corresponding to the given row number.
        Return an empty string if the row number is invalid.
        """
        if row < 0 or row >= self.rowCount():
            return ""
        return self.data(self.index(row), FILEPATH_ROLE)

    def hasFile(self, path: str) -> bool:
        """
        Return True if the given path is present in this model.
        """
        return path in self.fileRows

