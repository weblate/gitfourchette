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
        assert conflict.theirs is not None, "MergeDriver requires a 'theirs' side in DiffConflict"

        # Keep a reference to mergeDir so the temporary directory doesn't vanish
        self.mergeDir = tempfile.TemporaryDirectory(dir=qTempDir(), prefix="merge-", ignore_cleanup_errors=True)
        mergeDirPath = self.mergeDir.name

        # Dump OURS and THEIRS blobs into the temporary directory
        self.oursPath = dumpTempBlob(repo, mergeDirPath, conflict.ours, "OURS")
        self.theirsPath = dumpTempBlob(repo, mergeDirPath, conflict.theirs, "THEIRS")

        oursPath = conflict.ours.path
        baseName = os.path.basename(oursPath)
        self.targetPath = repo.in_workdir(oursPath)
        self.relativeTargetPath = oursPath

        if conflict.ancestor is not None:
            # Dump ANCESTOR blob into the temporary directory
            self.ancestorPath = dumpTempBlob(repo, mergeDirPath, conflict.ancestor, "ANCESTOR")
        else:
            # There's no ancestor! Some merge tools can fake a 3-way merge without
            # an ancestor (e.g. PyCharm), but others won't (e.g. VS Code).
            # To make sure we get a 3-way merge, copy our current workdir file as
            # the fake ANCESTOR file. It should contain chevron conflict markers
            # (<<<<<<< >>>>>>>) which should trigger conflicts between OURS and
            # THEIRS in the merge tool.
            self.ancestorPath = os.path.join(mergeDirPath, f"[NO-ANCESTOR]{baseName}")
            shutil.copyfile(self.targetPath, self.ancestorPath)

        # Create scratch file (merge tool output).
        # Some merge tools (such as VS Code) use the contents of this file
        # as a starting point, so copy the workdir version for this purpose.
        self.scratchPath = os.path.join(mergeDirPath, f"[MERGED]{baseName}")
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
