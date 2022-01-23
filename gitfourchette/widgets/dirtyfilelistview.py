from allqt import *
from widgets.filelistview import FileListView
from stagingstate import StagingState
from util import ActionDef
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
            ActionDef("&Open File in External Editor", self.openFile, icon=QStyle.SP_FileIcon),
            None,
            ActionDef("Open Containing &Folder", self.showInFolder, icon=QStyle.SP_DirIcon),
            ActionDef("&Copy Path", self.copyPaths),
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
        self.discardFiles.emit(list(self.selectedEntries()))
