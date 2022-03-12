from widgets.resetheaddialog import ResetHeadDialog
from . import reposcenario
from .fixtures import *
from .util import *
import pygit2


@withRepo("TestGitRepository")
@withPrep(None)
def testResetHeadToCommit(qtbot, workDirRepo, mainWindow, rw):
    oid1 = pygit2.Oid(hex="0966a434eb1a025db6b71485ab63a3bfbea520b6")

    assert workDirRepo.head.target != oid1  # make sure we're not starting from this commit
    assert workDirRepo.branches.local['master'].target != oid1

    rw.graphView.selectCommit(oid1)
    rw.graphView.resetHeadFlow()

    qd: ResetHeadDialog = findQDialog(rw, "reset head to 0966a4")
    qd.modeButtons['hard'].click()
    qd.accept()

    assert workDirRepo.head.target == oid1
    assert workDirRepo.branches.local['master'].target == oid1
