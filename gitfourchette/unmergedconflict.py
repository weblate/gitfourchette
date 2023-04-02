from gitfourchette import porcelain
from gitfourchette import tempdir
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.exttools import openInMergeTool
from gitfourchette.widgets.diffmodel import DiffConflict
import filecmp
import os
import pygit2
import shutil
import tempfile


class UnmergedConflict(QObject):
    mergeFailed = Signal()
    mergeComplete = Signal()

    def __init__(self, parent: QWidget, repo: pygit2.Repository, conflict: DiffConflict):
        super().__init__(parent)

        self.conflict = conflict
        self.repo = repo

        # Keep mergeDir around so the temp dir doesn't vanish
        self.mergeDir = tempfile.TemporaryDirectory(dir=tempdir.getSessionTemporaryDirectory(), prefix="merge-", ignore_cleanup_errors=True)
        mergeDirPath = self.mergeDir.name

        # TODO: do we always have an ancestor?
        self.ancestorPath = dumpTempBlob(repo, mergeDirPath, conflict.ancestor, "ANCESTOR")
        self.oursPath = dumpTempBlob(repo, mergeDirPath, conflict.ours, "OURS")
        self.theirsPath = dumpTempBlob(repo, mergeDirPath, conflict.theirs, "THEIRS")
        self.scratchPath = os.path.join(mergeDirPath, "[MERGED]" + os.path.basename(conflict.ours.path))

        # Make sure the output path exists so the FSW can begin watching it
        shutil.copyfile(porcelain.workdirPath(repo, self.conflict.ours.path), self.scratchPath)

        s = os.stat(self.scratchPath)

        self.process = None

    def startProcess(self):
        self.process = openInMergeTool(self, self.ancestorPath, self.oursPath, self.theirsPath, self.scratchPath)
        self.process.finished.connect(self.onMergeProcessFinished)

    def onMergeProcessFinished(self, exitCode: int, exitStatus: QProcess.ExitStatus):
        print("Merge tool exited with code", exitCode, exitStatus)

        if exitCode != 0 or exitStatus == QProcess.ExitStatus.CrashExit:
            self.mergeFailed.emit()
            return

        # If output file still contains original contents,
        # the merge tool probably hasn't done anything
        if filecmp.cmp(self.scratchPath, porcelain.workdirPath(self.repo, self.conflict.ours.path)):
            self.mergeFailed.emit()
            return

        qmb = asyncMessageBox(
            self.parent(),
            'information',
            self.tr("Merge conflict resolved"),
            paragraphs(
                self.tr("It looks like you’ve resolved the merge conflict in <b>“{0}”</b>.").format(self.conflict.ours.path),
                self.tr("Is that correct?")),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        qmb.button(QMessageBox.StandardButton.Ok).setText(self.tr("Confirm merge resolution"))
        qmb.accepted.connect(self.onAcceptMergedFile)
        qmb.rejected.connect(self.onRejectMergedFile)
        qmb.show()

    def onRejectMergedFile(self):
        self.deleteLater()

    def onAcceptMergedFile(self):
        with open(self.scratchPath, "rb") as scratchFile, \
                open(porcelain.workdirPath(self.repo, self.conflict.ours.path), "wb") as ourFile:
            data = scratchFile.read()
            ourFile.write(data)

        del self.repo.index.conflicts[self.conflict.ours.path]

        self.deleteLater()
