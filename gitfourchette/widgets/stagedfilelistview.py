from allqt import *
from stagingstate import StagingState
from widgets.filelistview import FileListView
import settings


class StagedFileListView(FileListView):
    patchApplied: Signal = Signal()

    def __init__(self, parent):
        super().__init__(parent, StagingState.STAGED)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def createContextMenuActions(self):
        return [
            ("&Unstage", self.unstage),
            (None, None)
        ] + super().createContextMenuActions()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT + settings.KEYS_REJECT:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        # everything that is staged is supposed to be a diff entry
        for entry in self.selectedEntries():
            assert entry.diff is not None
            self.git.restore(entry.diff.a_path, staged=True)
        self.patchApplied.emit()
