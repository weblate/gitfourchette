from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import tempdir
from gitfourchette.forms.prefsdialog import PrefsDialog
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.exttools import openInMergeTool, PREFKEY_MERGETOOL
from gitfourchette.diffview.specialdiff import DiffConflict
import filecmp
import os
import pygit2
import shutil
import tempfile


TAG = "UnmergedConflict"


class UnmergedConflict(QObject):
    mergeFailed = Signal()
    mergeComplete = Signal()

    process: QProcess | None

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

        self.process = None

        self.mergeFailed.connect(lambda: self.deleteLater())

    def startProcess(self):
        self.process = openInMergeTool(self.parent(), self.ancestorPath, self.oursPath, self.theirsPath, self.scratchPath)
        if self.process:
            self.process.finished.connect(self.onMergeProcessFinished)

    def onMergeProcessFinished(self, exitCode: int, exitStatus: QProcess.ExitStatus):
        log.info(TAG, "Merge tool exited with code", exitCode, exitStatus)

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
                self.tr("Do you want to keep this resolution?")),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        qmb.button(QMessageBox.StandardButton.Ok).setText(self.tr("Confirm resolution"))
        qmb.button(QMessageBox.StandardButton.Cancel).setText(self.tr("Discard resolution"))
        qmb.accepted.connect(self.mergeComplete)
        qmb.rejected.connect(self.mergeFailed)
        qmb.show()
