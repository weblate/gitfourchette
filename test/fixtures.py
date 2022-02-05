from gitfourchette.widgets.mainwindow import MainWindow
from gitfourchette.widgets.repowidget import RepoWidget
import os
import pytest
import tarfile
import tempfile
import pygit2


def withRepo(name):
    return pytest.mark.parametrize('testRepoName', [name])


def withPrep(fixture_name):
    return pytest.mark.parametrize('prep', [fixture_name])


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def workDir(tempDir, testRepoName, prep) -> str:
    testPath = os.path.realpath(__file__)
    testPath = os.path.dirname(testPath)

    with tarfile.open(F"{testPath}/data/{testRepoName}.tar") as tar:
        tar.extractall(tempDir.name)
    path = F"{tempDir.name}/{testRepoName}/"
    if prep:
        prep(path)
    return path


@pytest.fixture
def workDirRepo(workDir) -> pygit2.Repository:
    return pygit2.Repository(workDir)


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


@pytest.fixture
def rw(mainWindow, workDir) -> RepoWidget:
    return mainWindow.openRepo(workDir, addToHistory=False)


