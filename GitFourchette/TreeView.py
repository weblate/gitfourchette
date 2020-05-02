from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import MainWindow
import globals


class TreeView(QListView):
    rowstuff = []

    def __init__(self, parent: MainWindow.MainWindow):
        super(__class__, self).__init__(parent)
        self.uindo = parent
        self.setModel(QStandardItemModel())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setIconSize(QSize(16, 16))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers) # prevent editing text after double-clicking

    def clear(self):
        with self.uindo.unready():
            self.model().clear()
            self.rowstuff = []

    def fillDiff(self, diff):
        model: QStandardItemModel = self.model()
        for f in diff:
            self.rowstuff.append(f)
            item = QStandardItem(f.a_path)
            item.setIcon(globals.statusIcons[f.change_type])
            model.appendRow(item)

    def fillUntracked(self, untracked_files):
        model: QStandardItemModel = self.model()
        for f in untracked_files:
            self.rowstuff.append(f)
            item = QStandardItem(f + " (untracked)")
            item.setIcon(globals.statusIcons['A'])
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
            self.uindo.diffView.setFailureContents("Error\n" + "".join(traceback.TracebackException.from_exception(ex).format()))
        QApplication.restoreOverrideCursor()


class UnstagedView(TreeView):
    def __init__(self, parent: MainWindow.MainWindow):
        super(__class__, self).__init__(parent)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        action = QAction("Stage", self)
        action.triggered.connect(self.stage)
        self.addAction(action)

    def stage(self):
        git = self.uindo.state.repo.git
        for si in self.selectedIndexes():
            change = self.rowstuff[si.row()]
            print(F"Staging: {change.a_path}")
            git.add(change.a_path)
            #self.uindo.state.index.add(change.a_path) # <- also works at first... but might add too many things after repeated staging/unstaging??
        self.uindo.fillStageView()


class StagedView(TreeView):
    def __init__(self, parent: MainWindow.MainWindow):
        super(__class__, self).__init__(parent)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        action = QAction("UnStage", self)
        action.triggered.connect(self.unstage)
        self.addAction(action)

    def unstage(self):
        git = self.uindo.state.repo.git
        for si in self.selectedIndexes():
            change = self.rowstuff[si.row()]
            print(F"UnStaging: {change.a_path}")
            git.restore(change.a_path, staged=True)
        self.uindo.fillStageView()
