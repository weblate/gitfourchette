from __future__ import annotations
from pytestqt.qtbot import QtBot
from typing import TYPE_CHECKING
import pytest
import tempfile
import os

if TYPE_CHECKING:
    # For '-> MainWindow' type annotation, without pulling in MainWindow in the actual fixture
    from gitfourchette.mainwindow import MainWindow


@pytest.fixture(scope="session")
def qapp_args():
    mainPyPath = os.path.join(os.path.dirname(__file__), "..", "gitfourchette", "__main__.py")
    mainPyPath = os.path.normpath(mainPyPath)
    return [mainPyPath, "--test-mode", "--no-threads"]


@pytest.fixture(scope="session")
def qapp_cls():
    from gitfourchette.application import GFApplication
    yield GFApplication


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def mainWindow(qtbot: QtBot) -> MainWindow:
    from gitfourchette import settings, qt, trash
    from gitfourchette.mainwindow import MainWindow

    # Turn on test mode: Prevent loading/saving prefs; disable multithreaded work queue
    assert settings.TEST_MODE
    assert settings.SYNC_TASKS

    mw = MainWindow()

    # Don't let window linger in memory after this test
    mw.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

    # Let qtbot track the window and close it at the end of the test
    qtbot.addWidget(mw)

    qt.QApplication.setActiveWindow(mw)

    # Show window, which is required for some keyClicks calls to work.
    # If this inconveniences you, set the QT_QPA_PLATFORM=offscreen environment variable.
    mw.show()

    yield mw

    # Clear temp trash after this test
    trash.Trash.instance().clear()
