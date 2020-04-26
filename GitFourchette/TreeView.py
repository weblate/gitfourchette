from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import MainWindow


class TreeView(QListView):
    rowstuff = []

    def __init__(self, parent:MainWindow.MainWindow=None):
        super(__class__, self).__init__(parent)
        self.uindo = parent
        self.setModel(QStandardItemModel())

    def clear(self):
        self.model().clear()
        self.rowstuff = []

    def fill(self, diff, untracked_files=[], clr=True):
        if clr:
            self.clear()
        model:QStandardItemModel = self.model()
        for f in diff:
            self.rowstuff.append(f)
            #shitty = chr(ord('🄰') + ord(f.change_type[0]) - ord('A'))
            #item = QStandardItem(F"{shitty} {f.a_path}")
            item = QStandardItem(f.a_path)
            item.setIcon(QIcon(F"icons/status_{f.change_type[0].lower()}.svg"))
            self.setIconSize(QSize(16,16))
            model.appendRow(item)
        for f in untracked_files:
            self.rowstuff.append(f)
            item = QStandardItem(F"🅄 {f}")
            model.appendRow(item)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super(__class__, self).currentChanged(current, previous)
        if not self.uindo.isReady(): return
        if not current.isValid():
            self.uindo.diffView.clear()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            change = self.rowstuff[current.row()]
            self.uindo.diffView.setDiffContents(self.uindo.state.repo, change)
        except BaseException as ex:
            import traceback
            self.uindo.diffView.setShittyContents("Error\n" + "".join(traceback.TracebackException.from_exception(ex).format()))
        QApplication.restoreOverrideCursor()