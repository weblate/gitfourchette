from gitfourchette.mainwindow import MainWindow
from pytestqt.qtbot import QtBot
import pytest
import tempfile
import os


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def mainWindow(qtbot: QtBot) -> MainWindow:
    from gitfourchette import log, settings, qt

    log.VERBOSITY = 0

    # Turn on test mode: Prevent loading/saving prefs; disable multithreaded work queue
    settings.TEST_MODE = True
    settings.SYNC_TASKS = True

    # Set up resource search path. Not critical, but prevents spam about missing assets.
    assetsSearchPath = os.path.join(os.path.dirname(__file__), "..", "gitfourchette", "assets")
    qt.QDir.addSearchPath("assets", assetsSearchPath)

    mw = MainWindow()
    qtbot.addWidget(mw)

    qt.QApplication.setActiveWindow(mw)

    # mw.show()
    return mw
