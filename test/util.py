import tempfile

from . import *
import os
import re
import tarfile
import shutil
from gitfourchette.porcelain import *


TEST_SIGNATURE = Signature("Test Person", "toto@example.com", 1672600000, 0)


def unpackRepo(
        tempDir: tempfile.TemporaryDirectory | str,
        testRepoName="TestGitRepository",
        userName=TEST_SIGNATURE.name,
        userEmail=TEST_SIGNATURE.email,
        renameTo="",
) -> str:
    tempDirPath = tempDir if type(tempDir) is str else tempDir.name

    testPath = os.path.realpath(__file__)
    testPath = os.path.dirname(testPath)

    with tarfile.open(F"{testPath}/data/{testRepoName}.tar") as tar:
        tar.extractall(tempDirPath)

    path = F"{tempDirPath}/{testRepoName}"
    path = os.path.realpath(path)

    if renameTo:
        path2 = f"{tempDirPath}/{renameTo}"
        shutil.move(path, path2)
        path = path2

    path += "/"  # ease direct comparison with workdir path produced by libgit2 (it appends a slash)

    with open(F"{path}/.git/config", "at") as configFile:
        configFile.write(
            "\n[user]\n"
            F"name = {userName}\n"
            F"email = {userEmail}\n")

    return path


def makeBareCopy(path: str, addAsRemote: str, preFetch: bool, barePath=""):
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
            remote = repo.remotes.create(addAsRemote, barePath)  # TODO: Should we add file:// ?
            if preFetch:
                remote.fetch()

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


def readFile(path):
    with open(path, "rb") as f:
        return f.read()


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


def findMenuAction(menu: QMenu | QMenuBar, pattern: str):
    if isinstance(menu, QMenuBar):
        menuBar = menu
        menuName, pattern = pattern.split("/", 1)
        for menu in menuBar.children():
            if isinstance(menu, QMenu) and re.search(menuName, menu.title(), re.I):
                break
        else:
            assert False, "didn't find menu '{menuName}' in QMenuBar"

    assert isinstance(menu, QMenu)
    for action in menu.actions():
        actionText = re.sub(r"&([A-Za-z])", r"\1", action.text())
        if re.search(pattern, actionText, re.IGNORECASE):
            return action


def triggerMenuAction(menu: QMenu | QMenuBar, pattern: str):
    action = findMenuAction(menu, pattern)
    assert action is not None, f"did not find menu action matching \"{pattern}\""
    action.trigger()


def qteFind(qte: QTextEdit, pattern: str, plainText=False):
    if plainText:
        found = re.search(pattern, qte.toPlainText(), re.I | re.M)
    else:
        regex = QRegularExpression(pattern, QRegularExpression.PatternOption.CaseInsensitiveOption | QRegularExpression.PatternOption.MultilineOption)
        found = qte.find(regex)

    assert found
    return found


def qteClickLink(qte: QTextEdit, pattern: str):
    qteFind(qte, pattern)
    QTest.keyPress(qte, Qt.Key.Key_Enter)


def findQDialog(parent: QWidget, pattern: str) -> QDialog:
    dlg: QDialog
    for dlg in parent.findChildren(QDialog):
        if not dlg.isEnabled() or dlg.isHidden():
            continue
        if re.search(pattern, dlg.windowTitle(), re.IGNORECASE):
            return dlg

    assert False, F"did not find qdialog matching \"{pattern}\""


def findQMessageBox(parent: QWidget, textPattern: str):
    for qmb in parent.findChildren(QMessageBox):
        if not qmb.isVisibleTo(parent):  # skip zombie QMBs
            continue
        if re.search(textPattern, qmb.text(), re.IGNORECASE):
            return qmb

    assert False, F"did not find qmessagebox \"{textPattern}\""


def acceptQMessageBox(parent: QWidget, textPattern: str):
    findQMessageBox(parent, textPattern).accept()


def rejectQMessageBox(parent: QWidget, textPattern: str):
    findQMessageBox(parent, textPattern).reject()
