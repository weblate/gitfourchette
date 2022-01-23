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
            ActionDef("&Open File in External Editor", self.openFile, QStyle.SP_FileIcon),
            None,
            ActionDef("Open Containing &Folder", self.showInFolder, QStyle.SP_DirIcon),
            ActionDef("&Copy Path", self.copyPaths),
        ] + super().createContextMenuActions()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT + settings.KEYS_REJECT:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        self.unstageFiles.emit(list(self.selectedEntries()))
