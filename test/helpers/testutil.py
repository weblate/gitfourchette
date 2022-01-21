from helpers.qttest_imports import *
import pygit2
import os


def writeFile(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def qlvGetRowData(view: QListView):
    model = view.model()
    text = []
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        text.append(index.data(Qt.DisplayRole))
    return text


def qlvClickNthRow(view: QListView, n: int):
    index = view.model().index(n, 0)
    view.scrollTo(index)
    rect = view.visualRect(index)
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=rect.center())


def findMenuAction(menu: QMenu, subtext: str):
    subtext = subtext.upper()

    for action in menu.actions():
        if subtext in action.text().replace("&", "").upper():
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

