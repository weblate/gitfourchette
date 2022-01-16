import porcelain
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
                ActionDef("&Copy Path", self.copyPaths),
                ActionDef("Open Containing &Folder", self.showInFolder),
                None,
                ActionDef("Open Revision in External Editor", self.openRevision),
                ActionDef("Save Revision As...", self.saveRevisionAs),
                ]

    def clear(self):
        super().clear()
        self.commitOid = None

    def setCommit(self, oid: pygit2.Oid):
        self.commitOid = oid

    def openRevision(self):
        for entry in self.confirmSelectedEntries("open # files"):
            entryPath = entry.delta.new_file.path
            blob = porcelain.getFileRevision(self.repo, self.commitOid, entryPath)

            name, ext = os.path.splitext(blob.name)
            name = F"{name}@{shortHash(self.commitOid)}{ext}"

            tempPath = os.path.join(getSessionTemporaryDirectory(), name)

            with open(tempPath, "wb") as f:
                f.write(blob.data)

            QDesktopServices.openUrl(tempPath)

    def saveRevisionAs(self, saveInto=None):
        for entry in self.confirmSelectedEntries("save # files"):
            entryPath = entry.delta.new_file.path
            blob = porcelain.getFileRevision(self.repo, self.commitOid, entryPath)

            name, ext = os.path.splitext(blob.name)
            name = F"{name}@{shortHash(self.commitOid)}{ext}"

            if saveInto:
                savePath = os.path.join(saveInto, name)
            else:
                savePath, _ = QFileDialog.getSaveFileName(self, "Save file revision", name)

            if not savePath:
                continue

            with open(savePath, "wb") as f:
                f.write(blob.data)

            os.chmod(savePath, blob.filemode)
