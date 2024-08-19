import os.path
import shutil
from contextlib import suppress

import pytest

from gitfourchette import qt
from gitfourchette.application import GFApplication
from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.prefsdialog import PrefsDialog
from gitfourchette.forms.reposettingsdialog import RepoSettingsDialog
from gitfourchette.forms.unloadedrepoplaceholder import UnloadedRepoPlaceholder
from gitfourchette.graphview.commitlogmodel import SpecialRow
from gitfourchette.mainwindow import MainWindow
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.sidebar.sidebarmodel import EItem, SidebarNode
from .util import *


def testPrefsDialog(tempDir, mainWindow):
    def openPrefs() -> PrefsDialog:
        triggerMenuAction(mainWindow.menuBar(), "file/settings")
        return findQDialog(mainWindow, "settings")

    # Open a repo so that refreshPrefs functions are exercized in coverage
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    # Open prefs, reset to first tab to prevent spillage from any previous test
    dlg = openPrefs()
    dlg.tabs.setCurrentIndex(0)
    dlg.reject()

    # Open prefs, navigate to some tab and reject
    dlg = openPrefs()
    assert dlg.tabs.currentIndex() == 0
    dlg.tabs.setCurrentIndex(2)
    dlg.reject()

    # Open prefs again and check that the tab was restored
    dlg = openPrefs()
    assert dlg.tabs.currentIndex() == 2
    dlg.reject()

    # Change statusbar setting, and cancel
    assert mainWindow.statusBar().isVisible()
    dlg = openPrefs()
    checkBox: QCheckBox = dlg.findChild(QCheckBox, "prefctl_showStatusBar")
    assert checkBox.isChecked()
    checkBox.setChecked(False)
    dlg.reject()
    assert mainWindow.statusBar().isVisible()

    # Change statusbar setting, and accept
    dlg = openPrefs()
    checkBox: QCheckBox = dlg.findChild(QCheckBox, "prefctl_showStatusBar")
    assert checkBox.isChecked()
    checkBox.setChecked(False)
    dlg.accept()
    assert not mainWindow.statusBar().isVisible()


def testPrefsComboBoxWithPreview(tempDir, mainWindow):
    # Play with QComboBoxWithPreview (for coverage)
    dlg = mainWindow.openPrefsDialog("shortTimeFormat")
    comboBox: QComboBox = dlg.findChild(QWidget, "prefctl_shortTimeFormat").findChild(QComboBox)
    comboBox.setFocus()
    QTest.keyClick(comboBox, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    QTest.qWait(0)
    QTest.keyClick(comboBox, Qt.Key.Key_Down)
    QTest.qWait(0)
    QTest.keyClick(comboBox, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    QTest.qWait(0)  # trigger ItemDelegate.paint
    comboBox.setFocus()
    QTest.keyClicks(comboBox, "MMMM")  # trigger activation of out-of-bounds index
    QTest.keyClick(comboBox, Qt.Key.Key_Enter)
    dlg.reject()


def testPrefsFontControl(tempDir, mainWindow):
    # Open a repo so that refreshPrefs functions are exercized in coverage
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    rw.jump(NavLocator.inCommit(rw.repo.head_commit_id))
    defaultFamily = rw.diffView.document().defaultFont().family()
    randomFamily = next(family for family in QFontDatabase.families(QFontDatabase.WritingSystem.Latin)
                        if not QFontDatabase.isPrivateFamily(family))
    assert defaultFamily != randomFamily

    # Change font setting, and accept
    dlg = mainWindow.openPrefsDialog("font")
    fontWidget: QWidget = dlg.findChild(QWidget, "prefctl_font")
    resetFontButton: QPushButton = fontWidget.findChild(QAbstractButton, "ResetFontButton")
    assert not resetFontButton.isVisible()
    fontButton: QPushButton = fontWidget.findChild(QAbstractButton, "PickFontButton")
    fontButton.click()
    fontDialog: QFontDialog = dlg.findChild(QFontDialog)
    fontDialog.setCurrentFont(QFont(randomFamily))
    fontDialog.accept()
    dlg.accept()
    assert randomFamily == rw.diffView.document().defaultFont().family()

    dlg = mainWindow.openPrefsDialog("font")
    fontWidget: QWidget = dlg.findChild(QWidget, "prefctl_font")
    resetFontButton: QPushButton = fontWidget.findChild(QAbstractButton, "ResetFontButton")
    assert resetFontButton.isVisible()
    resetFontButton.click()
    assert not resetFontButton.isVisible()
    dlg.accept()
    assert defaultFamily == rw.diffView.document().defaultFont().family()


def testPrefsLanguageControl(tempDir, mainWindow):
    # Open a repo so that refreshPrefs functions are exercized in coverage
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    # Change font setting, and accept
    dlg = mainWindow.openPrefsDialog("language")
    comboBox: QComboBox = dlg.findChild(QWidget, "prefctl_language")
    qcbSetIndex(comboBox, "fran.ais")
    comboBox.activated.emit(comboBox.currentIndex())
    dlg.accept()
    acceptQMessageBox(mainWindow, "application des pr.f.rences")
