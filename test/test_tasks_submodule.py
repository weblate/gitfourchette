import pygit2.enums

from gitfourchette.nav import NavLocator
from . import reposcenario
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
import os
import pytest


def testOpenSubmoduleWithinApp(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.submodule(wd)

    rw = mainWindow.openRepo(wd)
    submoNode = next(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert "submo" == submoNode.data

    menu = rw.sidebar.makeNodeMenu(submoNode)

    assert mainWindow.currentRepoWidget() is rw
    triggerMenuAction(menu, r"open submodule.+tab")
    assert mainWindow.currentRepoWidget() is not rw
    assert mainWindow.currentRepoWidget().repo.workdir == os.path.join(wd, "submo/")


def testSubmoduleHeadUpdate(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    subWd = reposcenario.submodule(wd)
    subHead = Oid(hex='49322bb17d3acc9146f98c97d078513228bbf3c0')
    with RepoContext(subWd) as submo:
        submo.checkout_commit(subHead)

    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["submo"]
    assert qlvClickNthRow(rw.dirtyFiles, 0)

    special = rw.specialDiffView
    assert special.isVisibleTo(rw)
    assert qteFind(special, r"submodule.+submo.+was updated")
    assert qteFind(special, r"new:\s+49322bb", plainText=True)

    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)  # stage it
    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["submo"]


@pytest.mark.parametrize("discardMethod", ["key", "menu", "button", "link"])
def testSubmoduleDirty(qtbot, tempDir, mainWindow, discardMethod):
    wd = unpackRepo(tempDir)
    subWd = reposcenario.submodule(wd)
    writeFile(f"{subWd}/dirty.txt", "coucou")

    rw = mainWindow.openRepo(wd)

    assert rw.repo.status() == {"submo": FileStatus.WT_MODIFIED}
    assert qlvClickNthRow(rw.dirtyFiles, 0)

    special = rw.specialDiffView
    assert special.isVisibleTo(rw)
    assert qteFind(special, r"submodule.+submo.+was updated")
    assert qteFind(special, r"uncommitted changes")

    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)  # attempt to stage it
    assert rw.repo.status() == {"submo": FileStatus.WT_MODIFIED}  # shouldn't do anything (the actual app will emit a beep)

    if discardMethod == "key":
        QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Delete)  # attempt to discard it
    elif discardMethod == "menu":
        menu = rw.dirtyFiles.makeContextMenu()
        triggerMenuAction(menu, "discard.+submodule")
    elif discardMethod == "link":
        qteClickLink(special, r"discard them\.")
    elif discardMethod == "button":
        menu = rw.stageButton.menu()
        triggerMenuAction(menu, "discard")
    else:
        raise NotImplementedError("unknown discard method")

    acceptQMessageBox(rw, r"discard changes in submodule.+submo.+uncommitted changes")
    assert rw.repo.status() == {}  # should've cleared everything


def testAbsorbSubmodule(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    subWd = unpackRepo(wd, renameTo="submo")
    rw = mainWindow.openRepo(wd)
    assert rw.isVisibleTo(mainWindow)

    # Start without any submodules
    assert [] == rw.repo.listall_submodules_fast()
    assert [] == list(rw.sidebar.findNodesByKind(EItem.Submodule))

    # Select subfolder in dirty files
    rw.jump(NavLocator.inUnstaged("submo"))
    assert rw.specialDiffView.isVisibleTo(rw)
    assert "root of another git repo" in rw.specialDiffView.toPlainText().lower()

    # Click "absorb 'submo' as submodule" link
    foundLink = rw.specialDiffView.find(QRegularExpression(r"absorb.+as submodule"))
    assert foundLink
    QTest.keyPress(rw.specialDiffView, Qt.Key.Key_Enter)

    # Let AbsorbSubmodule run to completion
    dlg = findQDialog(rw, "absorb.+submodule")
    dlg.accept()

    # There must be a submodule now
    assert ["submo"] == rw.repo.listall_submodules_fast()
    assert "submo" == next(rw.sidebar.findNodesByKind(EItem.Submodule)).data

    # The submodule is there, but it's unstaged
    rw.jump(NavLocator.inStaged("submo"))

    # Click "open submodule" link
    qteClickLink(rw.specialDiffView, "open submodule")

    # That must have opened a new tab
    assert not rw.isVisibleTo(mainWindow)
    assert 2 == len(mainWindow.tabs)
    assert 1 == mainWindow.tabs.currentIndex()

    # Open superproject from tab context menu
    mainWindow.tabs.tabContextMenuRequested.emit(QPoint(0, 0), 1)
    tabMenu = mainWindow.findChild(QMenu, "MWRepoTabContextMenu")
    triggerMenuAction(tabMenu, r"open superproject")
    assert 0 == mainWindow.tabs.currentIndex()  # back to first tab
    assert rw is mainWindow.tabs.currentWidget()  # back to first tab
