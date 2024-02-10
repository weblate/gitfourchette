from gitfourchette.nav import NavLocator
from . import reposcenario
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
import os
import pytest


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
    foundLink = rw.specialDiffView.find("open submodule")
    assert foundLink
    QTest.keyPress(rw.specialDiffView, Qt.Key.Key_Enter)

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
