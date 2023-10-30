from dataclasses import dataclass
from typing import Any

import contextlib
import pygit2

from gitfourchette import log
from gitfourchette import settings
from gitfourchette.nav import NavContext
from gitfourchette.qt import *
from gitfourchette.toolbox import *

PATCH_ROLE = Qt.ItemDataRole.UserRole + 0
FILEPATH_ROLE = Qt.ItemDataRole.UserRole + 1


def deltaModeText(delta: pygit2.DiffDelta):
    om = delta.old_file.mode
    nm = delta.new_file.mode

    if om != 0 and nm != 0 and om != nm:
        # Mode change
        if nm == pygit2.GIT_FILEMODE_BLOB_EXECUTABLE:
            return "+x"
        elif om == pygit2.GIT_FILEMODE_BLOB_EXECUTABLE:
            return "-x"
        else:
            return ""
    elif om == 0:
        # New file
        if nm in [0, pygit2.GIT_FILEMODE_BLOB]:
            pass
        elif nm == pygit2.GIT_FILEMODE_BLOB_EXECUTABLE:
            return "+x"
        else:
            return translateFileMode(nm)


def fileTooltip(repo: pygit2.Repository, delta: pygit2.DiffDelta, isWorkdir: bool):
    if not delta:
        return ""

    locale = QLocale()
    of: pygit2.DiffFile = delta.old_file
    nf: pygit2.DiffFile = delta.new_file

    sc = delta.status_char()
    if delta.status == pygit2.GIT_DELTA_CONFLICTED:
        sc = "!"

    text = "<p style='white-space: pre'>" + escape(nf.path)
    text += "\n<table>"

    def newLine(heading, caption):
        return f"<tr><td><b>{heading} </b></tb><td>{caption}</td>"

    # Status caption
    statusCaption = translateDeltaStatus(sc)
    if sc not in '?!':  # show status char except for untracked and conflict
        statusCaption += f" ({sc})"
    text += newLine(translate("FileList", "status:"), statusCaption)

    # Similarity + Old name
    if sc == 'R':
        text += newLine(translate("FileList", "old name:"), escape(of.path))
        text += newLine(translate("FileList", "new name:"), escape(nf.path))
        text += newLine(translate("FileList", "similarity:"), f"{delta.similarity}%")

    # File Mode
    if sc not in 'D!':
        legend = translate("FileList", "file mode:")
        if sc in 'A?':
            text += newLine(legend, translateFileMode(nf.mode))
        elif of.mode != nf.mode:
            text += newLine(legend, f"{translateFileMode(of.mode)} &rarr; {translateFileMode(nf.mode)}")

    # Size (if available)
    if sc not in 'D!' and nf.size != 0 and (nf.mode & pygit2.GIT_FILEMODE_BLOB == pygit2.GIT_FILEMODE_BLOB):
        text += newLine(translate("FileList", "size:"), locale.formattedDataSize(nf.size))

    # Modified time
    if isWorkdir and sc not in 'D!':
        with contextlib.suppress(IOError):
            fullPath = os.path.join(repo.workdir, nf.path)
            fileStat = os.stat(fullPath)
            timeQdt = QDateTime.fromSecsSinceEpoch(int(fileStat.st_mtime))
            timeText = locale.toString(timeQdt, settings.prefs.shortTimeFormat)
            text += newLine(translate("FileList", "modified:"), timeText)

    return text


class FileListModel(QAbstractListModel):
    @dataclass
    class Entry:
        delta: pygit2.DiffDelta
        diff: pygit2.Diff
        patchNo: int

    entries: list[Entry]
    fileRows: dict[str, int]
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
    def repo(self) -> pygit2.Repository:
        return self.parent().repoWidget.state.repo

    def clear(self):
        self.entries = []
        self.fileRows = {}
        self.modelReset.emit()

    def setDiffs(self, diffs: list[pygit2.Diff]):
        self.beginResetModel()

        self.entries.clear()
        self.fileRows.clear()

        for diff in diffs:
            for patchNo, delta in enumerate(diff.deltas):
                if self.skipConflicts and delta.status == pygit2.GIT_DELTA_CONFLICTED:
                    continue
                self.fileRows[delta.new_file.path] = len(self.entries)
                self.entries.append(FileListModel.Entry(delta, diff, patchNo))

        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.entries)

    def getPatchAt(self, index: QModelIndex) -> pygit2.Patch:
        row = index.row()
        entry = self.entries[row]
        try:
            patch: pygit2.Patch = entry.diff[entry.patchNo]
            return patch
        except pygit2.GitError as e:
            log.warning("FileList", "GitError when attempting to get patch:", type(e).__name__, e)
            return None
        except OSError as e:
            # We might get here if the UI attempts to update itself while a long async
            # operation is ongoing. (e.g. a file is being recreated)
            log.warning("FileList", "UI attempting to update during async operation?", type(e).__name__, e)
            return None

    def getDeltaAt(self, index: QModelIndex) -> pygit2.DiffDelta:
        return self.entries[index.row()].delta

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == PATCH_ROLE:
            return self.getPatchAt(index)

        elif role == FILEPATH_ROLE or role == Qt.ItemDataRole.DisplayRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return "<NO DELTA>"

            path: str = self.getDeltaAt(index).new_file.path

            if role == Qt.ItemDataRole.DisplayRole:
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
            elif delta.status == pygit2.GIT_DELTA_UNTRACKED:
                iconName = "status_a"
            elif delta.status == pygit2.GIT_DELTA_CONFLICTED:
                iconName = "status_u"
            else:
                iconName = "status_" + delta.status_char().lower()
            return stockIcon(iconName)

        elif role == Qt.ItemDataRole.ToolTipRole:
            delta = self.getDeltaAt(index)
            return fileTooltip(self.repo, delta, self.navContext.isWorkdir())

        elif role == Qt.ItemDataRole.SizeHintRole:
            parentWidget: QWidget = self.parent()
            return QSize(-1, parentWidget.fontMetrics().height())

        return None

    def getRowForFile(self, path):
        return self.fileRows[path]

    def getFileAtRow(self, row: int):
        if row < 0 or row >= self.rowCount():
            return ""
        return self.data(self.index(row), FILEPATH_ROLE)

    def hasFile(self, path):
        return path in self.fileRows

