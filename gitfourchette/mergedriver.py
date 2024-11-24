# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import filecmp
import logging
import os
import shutil
import tempfile

from gitfourchette.porcelain import Repo, DiffConflict
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.exttools import openInExternalTool, PREFKEY_MERGETOOL

logger = logging.getLogger(__name__)


class MergeDriver(QObject):
    mergeFailed = Signal(int)
    mergeComplete = Signal()

    process: QProcess | None

    def __init__(self, parent: QWidget, repo: Repo, conflict: DiffConflict):
        super().__init__(parent)

        self.parentWidget = parent
        self.conflict = conflict
        self.process = None

        assert conflict.ours is not None, "MergeDriver requires an 'ours' side in DiffConflict"

        # Keep a reference to mergeDir so the temporary directory doesn't vanish
        self.mergeDir = tempfile.TemporaryDirectory(dir=qTempDir(), prefix="merge-", ignore_cleanup_errors=True)
        mergeDirPath = self.mergeDir.name

        self.ancestorPath = dumpTempBlob(repo, mergeDirPath, conflict.ancestor, "ANCESTOR")
        self.oursPath = dumpTempBlob(repo, mergeDirPath, conflict.ours, "OURS")
        self.theirsPath = dumpTempBlob(repo, mergeDirPath, conflict.theirs, "THEIRS")

        self.scratchPath = os.path.join(mergeDirPath, "[MERGED]" + os.path.basename(conflict.ours.path))
        self.relativeTargetPath = conflict.ours.path
        self.targetPath = repo.in_workdir(self.relativeTargetPath)

        # Make sure the output path exists so the FSW can begin watching it
        shutil.copyfile(self.targetPath, self.scratchPath)

        # Delete the QObject (along with its temporary directory) when the merge fails
        self.mergeFailed.connect(lambda: self.deleteLater())

    def startProcess(self):
        tokens = {
            "$B": self.ancestorPath,
            "$L": self.oursPath,
            "$R": self.theirsPath,
            "$M": self.scratchPath
        }
        self.process = openInExternalTool(self.parentWidget, PREFKEY_MERGETOOL, replacements=tokens, positional=[])
        if not self.process:
            return
        self.process.errorOccurred.connect(lambda: self.mergeFailed.emit(-1))
        self.process.finished.connect(self.onMergeProcessFinished)

    def onMergeProcessFinished(self, exitCode: int, exitStatus: QProcess.ExitStatus):
        self.process = None

        logger.info(f"Merge tool exited with code {exitCode}, {exitStatus}")

        if exitCode != 0 or exitStatus == QProcess.ExitStatus.CrashExit:
            self.mergeFailed.emit(exitCode)
            return

        # If output file still contains original contents,
        # the merge tool probably hasn't done anything
        if filecmp.cmp(self.scratchPath, self.targetPath):
            self.mergeFailed.emit(exitCode)
            return

        self.mergeComplete.emit()

    def copyScratchToTarget(self):
        shutil.copyfile(self.scratchPath, self.targetPath)
