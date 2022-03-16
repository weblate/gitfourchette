from gitfourchette.widgets.mainwindow import MainWindow
from pytestqt.qtbot import QtBot
import pytest
import tempfile


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def mainWindow(qtbot: QtBot) -> MainWindow:
    from gitfourchette import log
    log.VERBOSITY = 0

    # Turn on test mode: Prevent loading/saving prefs; disable multithreaded work queue
    from gitfourchette import settings
    settings.TEST_MODE = True

    mw = MainWindow()
    qtbot.addWidget(mw)

    # mw.show()
    return mw
