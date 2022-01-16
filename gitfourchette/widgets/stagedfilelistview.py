from allqt import *
from stagingstate import StagingState
from util import ActionDef
from widgets.filelistview import FileListView
import pygit2
import settings


class StagedFileListView(FileListView):
    unstageFiles: Signal = Signal(list)

    def __init__(self, parent):
        super().__init__(parent, StagingState.STAGED)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def createContextMenuActions(self):
        return [
            ActionDef("&Unstage", self.unstage, QStyle.SP_ArrowUp),
            None,
            ActionDef("&Copy Path", self.copyPaths),
            ActionDef("&Open File in External Editor", self.openFile),
            ActionDef("Open Containing &Folder", self.showInFolder),
        ] + super().createContextMenuActions()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT + settings.KEYS_REJECT:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        self.unstageFiles.emit(list(self.selectedEntries()))
