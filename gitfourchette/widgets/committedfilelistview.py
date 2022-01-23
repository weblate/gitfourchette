from allqt import *
from widgets.filelistview import FileListView
from stagingstate import StagingState
from util import ActionDef, shortHash
import pygit2
import os
from tempdir import getSessionTemporaryDirectory


class CommittedFileListView(FileListView):
    commitOid: pygit2.Oid | None

    def __init__(self, parent: QWidget):
        super().__init__(parent, StagingState.COMMITTED)
        self.commitOid = None

    def createContextMenuActions(self):
        return [
                ActionDef("Open Revision in External Editor", self.openRevision, QStyle.SP_FileIcon),
                ActionDef("Save Revision As...", self.saveRevisionAs, QStyle.SP_DialogSaveButton),
                None,
                ActionDef("Open Containing &Folder", self.showInFolder, QStyle.SP_DirIcon),
                ActionDef("&Copy Path", self.copyPaths),
                ]

    def clear(self):
        super().clear()
        self.commitOid = None

    def setCommit(self, oid: pygit2.Oid):
        self.commitOid = oid

    def openRevision(self):
        for diff in self.confirmSelectedEntries("open # files"):
            diffFile: pygit2.DiffFile
            if diff.delta.status == pygit2.GIT_DELTA_DELETED:
                diffFile = diff.delta.old_file
            else:
                diffFile = diff.delta.new_file

            blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

            name, ext = os.path.splitext(os.path.basename(diffFile.path))
            name = F"{name}@{shortHash(self.commitOid)}{ext}"

            tempPath = os.path.join(getSessionTemporaryDirectory(), name)

            with open(tempPath, "wb") as f:
                f.write(blob.data)

            QDesktopServices.openUrl(QUrl(tempPath))

    def saveRevisionAs(self, saveInto=None):
        for diff in self.confirmSelectedEntries("save # files"):
            diffFile: pygit2.DiffFile
            if diff.delta.status == pygit2.GIT_DELTA_DELETED:
                diffFile = diff.delta.old_file
            else:
                diffFile = diff.delta.new_file

            blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

            name, ext = os.path.splitext(os.path.basename(diffFile.path))
            name = F"{name}@{shortHash(self.commitOid)}{ext}"

            if saveInto:
                savePath = os.path.join(saveInto, name)
            else:
                savePath, _ = QFileDialog.getSaveFileName(self, "Save file revision", name)

            if not savePath:
                continue

            with open(savePath, "wb") as f:
                f.write(blob.data)

            os.chmod(savePath, diffFile.mode)
