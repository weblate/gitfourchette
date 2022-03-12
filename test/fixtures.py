from gitfourchette.widgets.mainwindow import MainWindow
import pytest
import tempfile


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def mainWindow() -> MainWindow:
    # Turn on test mode: Prevent loading/saving prefs; disable multithreaded work queue
    from gitfourchette import settings
    settings.TEST_MODE = True

    mw = MainWindow()
    #mw.show()
    yield mw

    # Tear down
    mw.close()

