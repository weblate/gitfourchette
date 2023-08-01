import contextlib
import errno

import pygit2

from gitfourchette import settings
from gitfourchette.exttools import openInTextEditor
from gitfourchette.filelists.filelist import FileList, SelectedFileBatchError
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.qt import *
from gitfourchette.tempdir import getSessionTemporaryDirectory
from gitfourchette.toolbox import *


class CommittedFiles(FileList):
    def __init__(self, parent: QWidget):
        super().__init__(parent, NavContext.COMMITTED)

    def createContextMenuActions(self, n):
        return [
            ActionDef(
                self.tr("Open Diff in New &Window"),
                self.wantOpenDiffInNewWindow,
            ),

            ActionDef(
                self.tr("Open &Diff(s) in {0}", "", n).format(settings.getDiffToolName()),
                self.wantOpenInDiffTool,
                icon="vcs-diff"
            ),

            ActionDef(
                self.tr("E&xport Diff(s) As Patch...", "", n),
                self.savePatchAs
            ),

            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("&Open File(s) in {0}", "", n).format(settings.getExternalEditorName()),
                icon=QStyle.StandardPixmap.SP_FileIcon, submenu=
                [
                    ActionDef(self.tr("Open Version &At {0}").format(shortHash(self.commitOid)), self.openNewRevision),
                    ActionDef(self.tr("Open Version &Before {0}").format(shortHash(self.commitOid)), self.openOldRevision),
                    ActionDef(self.tr("Open &Current Version"), self.openHeadRevision),
                ]
            ),

            ActionDef(
                self.tr("Sa&ve a Copy..."),
                icon=QStyle.StandardPixmap.SP_DialogSaveButton, submenu=
                [
                    ActionDef(self.tr("Save Version &At {0}").format(shortHash(self.commitOid)), self.saveNewRevision),
                    ActionDef(self.tr("Save Version &Before {0}".format(shortHash(self.commitOid))), self.saveOldRevision),
                ]
            ),

            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("Open &Folder(s)", "", n),
                self.showInFolder,
                QStyle.StandardPixmap.SP_DirIcon,
            ),

            ActionDef(
                self.tr("&Copy Path(s)", "", n),
                self.copyPaths,
                shortcuts=GlobalShortcuts.copy,
            ),

            self.pathDisplayStyleSubmenu()
        ]

    def setCommit(self, oid: pygit2.Oid):
        self.commitOid = oid

    def openNewRevision(self):
        self.openRevision(beforeCommit=False)

    def openOldRevision(self):
        self.openRevision(beforeCommit=True)

    def saveNewRevision(self):
        self.saveRevisionAs(beforeCommit=False)

    def saveOldRevision(self):
        self.saveRevisionAs(beforeCommit=True)

    def saveRevisionAsTempFile(self, diff, beforeCommit: bool = False):
        try:
            name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
        except FileNotFoundError as fnf:
            raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror)

        tempPath = os.path.join(getSessionTemporaryDirectory(), name)

        with open(tempPath, "wb") as f:
            f.write(blob.data)

        return tempPath

    def openRevision(self, beforeCommit: bool = False):
        def run(patch: pygit2.Patch):
            tempPath = self.saveRevisionAsTempFile(patch, beforeCommit)
            openInTextEditor(self, tempPath)

        if beforeCommit:
            title = self.tr("Open revision before commit")
        else:
            title = self.tr("Open revision at commit")

        self.confirmBatch(run, title,
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def saveRevisionAs(self, beforeCommit: bool = False, saveInto: str = ""):
        def dump(path: str, mode: int, data: bytes):
            with open(path, "wb") as f:
                f.write(data)
            os.chmod(path, mode)

        def run(diff):
            try:
                name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
            except FileNotFoundError as fnf:
                raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror)

            if saveInto:
                path = os.path.join(saveInto, name)
                dump(path, diffFile.mode, blob.data)
            else:
                qfd = PersistentFileDialog.saveFile(
                    self, "SaveFile", self.tr("Save file revision as"), name)
                qfd.fileSelected.connect(lambda path: dump(path, diffFile.mode, blob.data))
                qfd.show()

        if beforeCommit:
            title = self.tr("Save revision before commit")
        else:
            title = self.tr("Save revision at commit")

        self.confirmBatch(run, title, self.tr("Really export <b>{0} files</b>?"))

    def getFileRevisionInfo(self, patch: pygit2.Patch, beforeCommit: bool = False) -> tuple[str, pygit2.Blob, pygit2.DiffFile]:
        if beforeCommit:
            diffFile = patch.delta.old_file
            if patch.delta.status == pygit2.GIT_DELTA_ADDED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file didn’t exist before the commit."), diffFile.path)
        else:
            diffFile = patch.delta.new_file
            if patch.delta.status == pygit2.GIT_DELTA_DELETED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file was deleted by the commit."), diffFile.path)

        blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

        atSuffix = shortHash(self.commitOid)
        if beforeCommit:
            atSuffix = F"before-{atSuffix}"

        name, ext = os.path.splitext(os.path.basename(diffFile.path))
        name = F"{name}@{atSuffix}{ext}"

        return name, blob, diffFile

    def openHeadRevision(self):
        def run(patch: pygit2.Patch):
            diffFile = patch.delta.new_file
            path = os.path.join(self.repo.workdir, diffFile.path)
            if os.path.isfile(path):
                openInTextEditor(self, path)
            else:
                raise SelectedFileBatchError(self.tr("{0}: There’s no file at this path on HEAD.").format(diffFile.path))

        self.confirmBatch(run, self.tr("Open revision at HEAD"), self.tr("Really open <b>{0} files</b>?"))

    def wantOpenDiffInNewWindow(self):
        def run(patch: pygit2.Patch):
            self.openDiffInNewWindow.emit(patch, NavLocator(self.navContext, self.commitOid, patch.delta.new_file.path))

        self.confirmBatch(run, self.tr("Open diff in new window"), self.tr("Really open <b>{0} files</b>?"))
