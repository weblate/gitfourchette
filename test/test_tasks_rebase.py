# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.forms.rebasedialog import RebaseDialog
from gitfourchette.nav import NavLocator
from .util import *


def testRebaseDialog(tempDir, mainWindow, taskThread):
    wd = unpackRepo(tempDir)

    mainWindow.openRepo(wd)
    rw = waitForRepoWidget(mainWindow)
    rw.jump(NavLocator.inCommit(Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0"), "a/a1"), check=True)

    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)
    rebaseDialog.reject()

    waitUntilTrue(lambda: not rw.taskRunner.isBusy())
    rejectQMessageBox(rw, "exited with code")
