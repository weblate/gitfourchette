from dataclasses import dataclass
from typing import Any

import pygit2

from gitfourchette import log
from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.toolbox import *

# If SVG icons don't show up, you may need to install the 'qt6-svg' package.
STATUS_ICONS = {}
for status in "ACDMRTUX":
    STATUS_ICONS[status] = QIcon(F"assets:status_{status.lower()}.svg")

FALLBACK_STATUS_ICON = QIcon("assets:status_fallback.svg")

PATCH_ROLE = Qt.ItemDataRole.UserRole + 0
FILEPATH_ROLE = Qt.ItemDataRole.UserRole + 1


class FileListModel(QAbstractListModel):
    @dataclass
    class Entry:
        delta: pygit2.DiffDelta
        diff: pygit2.Diff
        patchNo: int

    entries: list[Entry]
    fileRows: dict[str, int]

    def __init__(self, parent):
        super().__init__(parent)
        self.clear()

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
                modeInfo = ""
                om = delta.old_file.mode
                nm = delta.new_file.mode
                if om != 0 and nm != 0 and om != nm:
                    # Mode change
                    if nm == pygit2.GIT_FILEMODE_BLOB_EXECUTABLE:
                        modeInfo = "+x"
                    elif om == pygit2.GIT_FILEMODE_BLOB_EXECUTABLE:
                        modeInfo = "-x"
                elif om == 0:
                    # New file
                    if nm in [0, pygit2.GIT_FILEMODE_BLOB]:
                        pass
                    elif nm == pygit2.GIT_FILEMODE_LINK:
                        modeInfo = "link"
                    elif nm == pygit2.GIT_FILEMODE_BLOB_EXECUTABLE:
                        modeInfo = "+x"
                    else:
                        modeInfo = f"{delta.new_file.mode:o}"
                if modeInfo:
                    path = f"[{modeInfo}] {path}"

            return path

        elif role == Qt.ItemDataRole.DecorationRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return FALLBACK_STATUS_ICON
            elif delta.status == pygit2.GIT_DELTA_UNTRACKED:
                return STATUS_ICONS.get('A', FALLBACK_STATUS_ICON)
            else:
                return STATUS_ICONS.get(delta.status_char(), FALLBACK_STATUS_ICON)

        elif role == Qt.ItemDataRole.ToolTipRole:
            delta = self.getDeltaAt(index)

            if not delta:
                return None

            if delta.status == pygit2.GIT_DELTA_UNTRACKED:
                return (
                        "<b>" + translate("FileList", "untracked file") + "</b><br>" +
                        F"{escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                )
            elif delta.status == pygit2.GIT_DELTA_CONFLICTED:
                conflictedText = translate("FileList", "merge conflict")

                return (
                    f"<b>{conflictedText}</b><br>"
                )
            else:
                fromText = translate("FileList", "from:")
                toText = translate("FileList", "to:")
                opText = translate("FileList", "status:")

                # see git_diff_status_char (diff_print.c)
                operationCaptions = {
                    "A": translate("FileList", "(added)"),
                    "C": translate("FileList", "(copied)"),
                    "D": translate("FileList", "(deleted)"),
                    "I": translate("FileList", "(ignored)"),
                    "M": translate("FileList", "(modified)"),
                    "R": translate("FileList", "(renamed, {0}% similarity)"),
                    "T": translate("FileList", "(file type changed)"),
                    "U": translate("FileList", "(updated but unmerged)"),
                    "X": translate("FileList", "(unreadable)"),
                    "?": translate("FileList", "(untracked)"),
                }

                try:
                    opCap = operationCaptions[delta.status_char()]
                    if delta.status == pygit2.GIT_DELTA_RENAMED:
                        opCap = opCap.format(delta.similarity)

                except KeyError:
                    opCap = ''

                return (
                    "<p style='white-space: pre'>"
                    F"<b>{opText} </b> {delta.status_char()} {opCap}"
                    F"\n<b>{fromText} </b> {escape(delta.old_file.path)} ({delta.old_file.mode:o})"
                    F"\n<b>{toText} </b> {escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                )

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


