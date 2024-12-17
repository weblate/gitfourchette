# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import errno
import os

from gitfourchette import settings
from gitfourchette.exttools import openInTextEditor
from gitfourchette.filelists.filelist import FileList, SelectedFileBatchError
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks import RestoreRevisionToWorkdir
from gitfourchette.toolbox import *


class CommittedFiles(FileList):
    def __init__(self, parent: QWidget):
        super().__init__(parent, NavContext.COMMITTED)

    def contextMenuActions(self, patches: list[Patch]) -> list[ActionDef]:
        actions = []

        n = len(patches)
        modeSet = {patch.delta.new_file.mode for patch in patches}
        anySubmodules = FileMode.COMMIT in modeSet
        onlySubmodules = anySubmodules and len(modeSet) == 1

        if not anySubmodules:
            actions += [
                ActionDef(
                    self.tr("Open Diff in New &Window"),
                    self.wantOpenDiffInNewWindow,
                ),

                *self.contextMenuActionsDiff(patches),

                ActionDef.SEPARATOR,

                ActionDef(
                    self.tr("&Revert This Change...", "", n),
                    self.revertPaths,
                ),

                ActionDef(
                    self.tr("Restor&e File Revision..."),
                    submenu=[
                        ActionDef(self.tr("&As Of This Commit"), self.restoreNewRevision),
                        ActionDef(self.tr("&Before This Commit"), self.restoreOldRevision),
                    ]
                ),

                ActionDef.SEPARATOR,

                ActionDef(
                    self.tr("&Open File in {0}", "", n).format(settings.getExternalEditorName()),
                    icon="SP_FileIcon", submenu=[
                        ActionDef(self.tr("&As Of This Commit"), self.openNewRevision),
                        ActionDef(self.tr("&Before This Commit"), self.openOldRevision),
                        ActionDef(self.tr("&Current Revision (Working Copy)"), self.openWorkingCopyRevision),
                    ]
                ),

                ActionDef(
                    self.tr("&Save a Copy..."),
                    icon="SP_DialogSaveButton", submenu=[
                        ActionDef(self.tr("&As Of This Commit"), self.saveNewRevision),
                        ActionDef(self.tr("&Before This Commit"), self.saveOldRevision),
                    ]
                ),
            ]

        elif onlySubmodules:
            actions += [
                ActionDef(
                    self.tr("%n Submodules", "please omit %n in singular form", n),
                    kind=ActionDef.Kind.Section,
                ),

                ActionDef(
                    self.tr("Open %n Submodules in New Tabs", "please omit %n in singular form", n),
                    self.openSubmoduleTabs,
                ),
            ]

        else:
            sorry = translate("FileList", "Please review the files individually.")
            actions += [
                ActionDef(sorry, enabled=False),
            ]

        actions += super().contextMenuActions(patches)
        return actions

    def setCommit(self, oid: Oid):
        self.commitId = oid

    def openNewRevision(self):
        self.openRevision(beforeCommit=False)

    def openOldRevision(self):
        self.openRevision(beforeCommit=True)

    def saveNewRevision(self):
        self.saveRevisionAs(beforeCommit=False)

    def saveOldRevision(self):
        self.saveRevisionAs(beforeCommit=True)

    def restoreNewRevision(self):
        patches = list(self.selectedPatches())
        assert len(patches) == 1
        RestoreRevisionToWorkdir.invoke(self, patches[0], old=False)

    def restoreOldRevision(self):
        patches = list(self.selectedPatches())
        assert len(patches) == 1
        RestoreRevisionToWorkdir.invoke(self, patches[0], old=True)

    def saveRevisionAsTempFile(self, patch: Patch, beforeCommit: bool = False):
        try:
            name, blob, _ = self.getFileRevisionInfo(patch, beforeCommit)
        except FileNotFoundError as fnf:
            raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror) from fnf

        tempPath = os.path.join(qTempDir(), name)

        with open(tempPath, "wb") as f:
            f.write(blob.data)

        return tempPath

    # TODO: Send all files to text editor in one command?
    def openRevision(self, beforeCommit: bool = False):
        def run(patch: Patch):
            tempPath = self.saveRevisionAsTempFile(patch, beforeCommit)
            openInTextEditor(self, tempPath)

        if beforeCommit:
            title = self.tr("Open revision before commit")
        else:
            title = self.tr("Open revision at commit")

        self.confirmBatch(run, title,
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    # TODO: Perhaps this could be a RepoTask?
    def saveRevisionAs(self, beforeCommit: bool = False):
        def dump(path: str, mode: int, data: bytes):
            with open(path, "wb") as f:
                f.write(data)
            os.chmod(path, mode)

        def run(patch: Patch):
            try:
                name, blob, diffFile = self.getFileRevisionInfo(patch, beforeCommit)
            except FileNotFoundError as fnf:
                raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror) from fnf

            qfd = PersistentFileDialog.saveFile(self, "SaveFile", self.tr("Save file revision as"), name)
            qfd.fileSelected.connect(lambda path: dump(path, diffFile.mode, blob.data))
            qfd.show()

        if beforeCommit:
            title = self.tr("Save revision before commit")
        else:
            title = self.tr("Save revision at commit")

        self.confirmBatch(run, title, self.tr("Really export <b>{0} files</b>?"))

    def getFileRevisionInfo(self, patch: Patch, beforeCommit: bool = False) -> tuple[str, Blob, DiffFile]:
        if beforeCommit:
            diffFile = patch.delta.old_file
            if patch.delta.status == DeltaStatus.ADDED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file didn’t exist before the commit."), diffFile.path)
        else:
            diffFile = patch.delta.new_file
            if patch.delta.status == DeltaStatus.DELETED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file was deleted by the commit."), diffFile.path)

        blob = self.repo.peel_blob(diffFile.id)

        atSuffix = shortHash(self.commitId)
        if beforeCommit:
            atSuffix = F"before-{atSuffix}"

        name, ext = os.path.splitext(os.path.basename(diffFile.path))
        name = F"{name}@{atSuffix}{ext}"

        return name, blob, diffFile

    def openWorkingCopyRevision(self):
        def run(patch: Patch):
            diffFile = patch.delta.new_file
            path = self.repo.in_workdir(diffFile.path)
            if os.path.isfile(path):
                openInTextEditor(self, path)
            else:
                raise SelectedFileBatchError(self.tr("{0}: There’s no file at this path in the working copy.").format(diffFile.path))

        self.confirmBatch(run, self.tr("Open working copy revision"), self.tr("Really open <b>{0} files</b>?"))

    def wantOpenDiffInNewWindow(self):
        def run(patch: Patch):
            self.openDiffInNewWindow.emit(patch, NavLocator(self.navContext, self.commitId, patch.delta.new_file.path))

        self.confirmBatch(run, self.tr("Open diff in new window"), self.tr("Really open <b>{0} windows</b>?"))
