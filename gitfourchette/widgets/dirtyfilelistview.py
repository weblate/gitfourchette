from allqt import *
from widgets.filelistview import FileListView
from stagingstate import StagingState
from util import ActionDef
import pygit2
import settings


class DirtyFileListView(FileListView):
    stageFiles = Signal(list)
    discardFiles = Signal(list)

    def __init__(self, parent):
        super().__init__(parent, StagingState.UNSTAGED)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def createContextMenuActions(self):
        return [
            ActionDef("&Stage", self.stage, QStyle.SP_ArrowDown),
            ActionDef("&Discard Changes", self.discard, QStyle.SP_TrashIcon),
            None,
            ActionDef("&Copy Path", self.copyPaths),
            ActionDef("&Open File in External Editor", self.openFile),
            ActionDef("Open Containing &Folder", self.showInFolder),
        ]

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            self.stage()
        elif k in settings.KEYS_REJECT:
            self.discard()
        else:
            super().keyPressEvent(event)

    def stage(self):
        self.stageFiles.emit(list(self.selectedEntries()))

    def discard(self):
        entries = list(self.selectedEntries())

        if len(entries) == 1:
            question = F"Really discard changes to {entries[0].delta.new_file.path}?"
        else:
            question = F"Really discard changes to {len(entries)} files?"

        qmb = QMessageBox(
            QMessageBox.Question,
            "Discard changes",
            F"{question}\nThis cannot be undone!",
            QMessageBox.Discard | QMessageBox.Cancel,
            parent=self)

        yes: QAbstractButton = qmb.button(QMessageBox.Discard)
        yes.setText("Discard changes")
        yes.clicked.connect(lambda: self.discardFiles.emit(entries))
        qmb.setDefaultButton(yes)

        qmb.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()
