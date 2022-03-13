from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.commitdialog import CommitDialog
import pygit2


def testSensibleMessageShownForUnstagedEmptyFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/NewEmptyFile.txt")
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.dirtyFiles, 0)

    assert not rw.diffView.isVisibleTo(rw)
    assert rw.richDiffView.isVisibleTo(rw)
    assert "is empty" in rw.richDiffView.toPlainText().lower()
