import os
import re
import shutil
import tempfile
from pathlib import Path

import pygit2

from gitfourchette.porcelain import *
from . import *

TEST_SIGNATURE = Signature("Test Person", "toto@example.com", 1672600000, 0)


def pause(seconds: int = 3):
    QTest.qWait(seconds * 1000)


def pygit2OlderThan(version: str):
    return not pygit2_version_at_least(version, raise_error=False)


def getTestDataPath(name):
    path = Path(__file__).resolve().parent / "data"
    return str(path / name)


def clearSessionwideIdentity():
    config = pygit2.Config.get_global_config()
    toClear = {
        "user.name": TEST_SIGNATURE.name,
        "user.email": TEST_SIGNATURE.email,
    }
    for key, expectedValue in toClear.items():
        assert config[key] == expectedValue
        del config[key]
        assert key not in config


def unpackRepo(
        tempDir: tempfile.TemporaryDirectory | str,
        testRepoName="TestGitRepository",
        renameTo="",
) -> str:
    tempDirPath = tempDir if type(tempDir) is str else tempDir.name

    path = f"{tempDirPath}/{testRepoName}"
    path = os.path.realpath(path)
    assert not os.path.exists(path)

    for ext in ".tar", ".zip":
        archivePath = getTestDataPath(f"{testRepoName}{ext}")
        if os.path.isfile(archivePath):
            shutil.unpack_archive(archivePath, os.path.dirname(path))
            assert os.path.isdir(path)
            break
    else:
        raise FileNotFoundError(f"can't find archive '{testRepoName}' in test data")

    if renameTo:
        path2 = f"{tempDirPath}/{renameTo}"
        shutil.move(path, path2)
        path = path2

    assert not path.endswith("/")
    path += "/"  # ease direct comparison with workdir path produced by libgit2 (it appends a slash)

    return path


def makeBareCopy(path: str, addAsRemote: str, preFetch: bool, barePath="", keepOldUpstream=False):
    if not barePath:
        basename = os.path.basename(os.path.normpath(path))  # normpath first, because basename may return an empty string if path ends with a slash
        barePath = f"{path}/../{basename}-bare.git"  # create bare repo besides real repo in temporary directory
    barePath = os.path.normpath(barePath)

    shutil.copytree(F"{path}/.git", barePath)

    conf = GitConfig(F"{barePath}/config")
    conf['core.bare'] = True
    del conf

    if addAsRemote:
        with RepoContext(path) as repo:
            remote = repo.remotes.create(addAsRemote, barePath)
            if preFetch:
                remote.fetch()
                if not keepOldUpstream:
                    for localBranch in repo.branches.local:
                        repo.edit_upstream_branch(localBranch, f"{addAsRemote}/{localBranch}")

    return barePath


def touchFile(path):
    open(path, 'a').close()

    # Also gotta do this for QFileSystemWatcher to pick up a change in a unit testing environment
    os.utime(path, (0, 0))


def writeFile(path, text):
    # Prevent accidental littering of current working directory
    assert os.path.isabs(path), "pass me an absolute path"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def readFile(path, timeout=0, unlink=False):
    while timeout > 0 and not os.path.exists(path):
        wait = 10
        QTest.qWait(wait)
        timeout -= wait
    with open(path, "rb") as f:
        data = f.read()
    if unlink:
        os.unlink(path)
    return data


def qlvGetRowData(view: QListView, role=Qt.ItemDataRole.DisplayRole):
    model = view.model()
    data = []
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        assert index.isValid()
        data.append(index.data(role))
    return data


def qlvFindRow(view: QListView, data: str, role=Qt.ItemDataRole.DisplayRole):
    model = view.model()
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        assert index.isValid()
        if index.data(role) == data:
            return row
    raise IndexError(f"didn't find a row containing '{data}'")


def qlvClickNthRow(view: QListView, n: int):
    index = view.model().index(n, 0)
    assert index.isValid()
    view.scrollTo(index)
    rect = view.visualRect(index)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    return index.data(Qt.ItemDataRole.DisplayRole)


def qlvGetSelection(view: QListView, role=Qt.ItemDataRole.DisplayRole):
    data = []
    for index in view.selectedIndexes():
        assert index.isValid()
        data.append(index.data(role))
    return data


def findMenuAction(menu: QMenu | QMenuBar, pattern: str) -> QAction:
    def stripAmps(s: str):
        return s.replace("&", "")

    patternParts = pattern.split("/")

    for submenuPattern in patternParts[:-1]:
        for submenu in menu.children():
            if (isinstance(submenu, QAction)
                    and submenu.menu()
                    and re.search(submenuPattern, stripAmps(submenu.text()), re.I)):
                menu = submenu.menu()
                break
            elif (isinstance(submenu, QMenu)
                  and re.search(submenuPattern, stripAmps(submenu.title()), re.I)):
                menu = submenu
                break
        else:
            assert False, f"didn't find menu '{pattern}' (failed pattern part: '{submenuPattern}')"

    assert isinstance(menu, QMenu)
    for action in menu.actions():
        actionText = re.sub(r"&([A-Za-z])", r"\1", action.text())
        if re.search(patternParts[-1], actionText, re.IGNORECASE):
            return action
    assert False, f"didn't find menu item '{pattern}' in menu"


def triggerMenuAction(menu: QMenu | QMenuBar, pattern: str):
    action = findMenuAction(menu, pattern)
    assert action is not None, f"did not find menu action matching \"{pattern}\""
    action.trigger()


def qteFind(qte: QTextEdit, pattern: str, plainText=False):
    assert isinstance(qte, QTextEdit)
    if plainText:
        found = re.search(pattern, qte.toPlainText(), re.I | re.M | re.DOTALL)
    else:
        # qte.find() starts searching at current cursor position, so reset cursor to top of document
        textCursor = qte.textCursor()
        textCursor.setPosition(0)
        qte.setTextCursor(textCursor)

        regex = QRegularExpression(pattern, QRegularExpression.PatternOption.CaseInsensitiveOption | QRegularExpression.PatternOption.MultilineOption | QRegularExpression.PatternOption.DotMatchesEverythingOption)
        found = qte.find(regex)

    assert found
    return found


def qteClickLink(qte: QTextEdit, pattern: str):
    qteFind(qte, pattern)
    QTest.keyPress(qte, Qt.Key.Key_Enter)


def qcbSetIndex(qcb: QComboBox, pattern: str):
    i = qcb.findText(pattern, Qt.MatchFlag.MatchRegularExpression)
    assert i >= 0
    qcb.setCurrentIndex(i)
    return i


def findQDialog(parent: QWidget, pattern: str) -> QDialog:
    dlg: QDialog
    for dlg in parent.findChildren(QDialog):
        if not dlg.isEnabled() or dlg.isHidden():
            continue
        if re.search(pattern, dlg.windowTitle(), re.IGNORECASE):
            return dlg

    assert False, F"did not find qdialog matching \"{pattern}\""


def waitFor(callable, timeout=5000, interval=100):
    interval = 100
    timeout = 5000
    assert timeout >= interval
    for i in range(0, timeout, interval):
        try:
            return callable()
        except AssertionError:
            QTest.qWait(interval)
    assert False, f"retry failed after {timeout} ms timeout"


def waitForQDialog(parent: QWidget, pattern: str) -> QDialog:
    return waitFor(lambda: findQDialog(parent, pattern))


def findQMessageBox(parent: QWidget, textPattern: str) -> QMessageBox:
    for qmb in parent.findChildren(QMessageBox):
        qmb: QMessageBox
        if not qmb.isVisibleTo(parent):  # skip zombie QMBs
            continue
        haystack = "\n".join([qmb.windowTitle(), qmb.text(), qmb.informativeText()])
        if re.search(textPattern, haystack, re.IGNORECASE | re.DOTALL):
            return qmb

    assert False, F"did not find qmessagebox \"{textPattern}\""


def acceptQMessageBox(parent: QWidget, textPattern: str):
    findQMessageBox(parent, textPattern).accept()
    parent.activateWindow()  # in offscreen tests, accepting the QMB doesn't restore an active window, for some reason (as of Qt 6.7.1)


def rejectQMessageBox(parent: QWidget, textPattern: str):
    findQMessageBox(parent, textPattern).reject()


def acceptQFileDialog(parent: QWidget, textPattern: str, path: str, useSuggestedName=False):
    qfd: QFileDialog = findQDialog(parent, textPattern)
    assert isinstance(qfd, QFileDialog)

    if useSuggestedName:
        suggestedName = os.path.basename(qfd.selectedFiles()[0])
        path = os.path.join(path, suggestedName)
    path = os.path.normpath(path)

    qfd.selectFile(path)
    qfd.show()
    qfd.accept()
    return path


def findQToolButton(parent: QToolButton, textPattern: str) -> QToolButton:
    for button in parent.findChildren(QToolButton):
        button: QToolButton
        if re.search(textPattern, button.text(), re.IGNORECASE | re.DOTALL):
            return button

    assert False, F"did not find QToolButton \"{textPattern}\""

