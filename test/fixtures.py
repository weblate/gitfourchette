from __future__ import annotations
from pytestqt.qtbot import QtBot
from typing import TYPE_CHECKING
import pytest
import tempfile
import os

if TYPE_CHECKING:
    # For '-> MainWindow' type annotation, without pulling in MainWindow in the actual fixture
    from gitfourchette.mainwindow import MainWindow


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def mainWindow(qtbot: QtBot) -> MainWindow:
    from gitfourchette import settings, qt
    from gitfourchette.mainwindow import MainWindow

    # Turn on test mode: Prevent loading/saving prefs; disable multithreaded work queue
    settings.TEST_MODE = True
    settings.SYNC_TASKS = True

    # Set up resource search path. Not critical, but prevents spam about missing assets.
    assetsSearchPath = os.path.join(os.path.dirname(__file__), "..", "gitfourchette", "assets")
    qt.QDir.addSearchPath("assets", assetsSearchPath)

    mw = MainWindow()

    # Don't let window linger in memory after this test
    mw.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

    # Initialize translation tables (translated texts are needed for some tests)
    from gitfourchette.trtables import TrTables
    TrTables.retranslateAll()

    # Let qtbot track the window and close it at the end of the test
    qtbot.addWidget(mw)

    qt.QApplication.setActiveWindow(mw)

    # mw.show()
    return mw
