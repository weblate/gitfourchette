from gitfourchette.allqt import *
from PySide2.QtTest import QTest
import pygit2
import binascii
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
    #self.breathe()


def hexToOid(hexstr: str):
    assert len(hexstr) == 40
    return pygit2.Oid(binascii.unhexlify(hexstr))

