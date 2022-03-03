from . import *
import pygit2
import os
import re


def touchFile(path):
    open(path, 'a').close()


def writeFile(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def qlvGetRowData(view: QListView, role=Qt.DisplayRole):
    model = view.model()
    data = []
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        data.append(index.data(role))
    return data


def qlvClickNthRow(view: QListView, n: int):
    index = view.model().index(n, 0)
    view.scrollTo(index)
    rect = view.visualRect(index)
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=rect.center())


def qlvGetSelection(view: QListView, role=Qt.DisplayRole):
    data = []
    for index in view.selectedIndexes():
        data.append(index.data(role))
    return data


def findMenuAction(menu: QMenu, pattern: str):
    for action in menu.actions():
        actionText = re.sub(r"&([A-Za-z])", r"\1", action.text())
        if re.search(pattern, actionText, re.IGNORECASE):
            return action


def findQDialog(parent: QWidget, subtext: str) -> QDialog:
    subtext = subtext.upper()

    dlg: QDialog
    for dlg in parent.findChildren(QDialog):
        if not dlg.isEnabled() or dlg.isHidden():
            continue
        if subtext in dlg.windowTitle().upper():
            return dlg

    assert False, F"did not find qdialog \"{subtext}\""


def acceptQMessageBox(parent: QWidget, subtext: str):
    subtext = subtext.upper()

    for qmb in parent.findChildren(QMessageBox):
        if subtext in qmb.windowTitle().upper():
            qmb.accept()
            return

    assert False, F"did not find qmessagebox \"{subtext}\""


def hexToOid(hexstr: str):
    assert len(hexstr) == 40
    return pygit2.Oid(hex=hexstr)
