from allqt import *
from stagingstate import StagingState
from util import ActionDef
from widgets.filelistview import FileListView
import pygit2
import settings


class StagedFileListView(FileListView):
    patchApplied: Signal = Signal()

    def __init__(self, parent):
        super().__init__(parent, StagingState.STAGED)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def createContextMenuActions(self):
        return [
            ActionDef("&Unstage", self.unstage, QStyle.SP_ArrowUp),
            None,
            ActionDef("&Open File in External Editor", self.openFile),
        ] + super().createContextMenuActions()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT + settings.KEYS_REJECT:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        index = self.repo.index
        head = self.repo.revparse_single('HEAD')
        for entry in self.selectedEntries():
            assert entry.patch, "a FileListEntry representing a staged file is supposed to contain a valid patch"
            delta : pygit2.DiffDelta = entry.patch.delta
            old_path = delta.old_file.path
            new_path = delta.new_file.path
            if delta.status == pygit2.GIT_DELTA_ADDED:
                assert old_path not in head.tree
                index.remove(old_path)
            elif delta.status == pygit2.GIT_DELTA_RENAMED:
                # TODO: Two-step removal to completely unstage a rename -- is this what we want?
                assert new_path in index
                index.remove(new_path)
            else:
                assert old_path in head.tree
                obj = head.tree[old_path]
                index.add(pygit2.IndexEntry(old_path, obj.oid, obj.filemode))
        index.write()
        self.patchApplied.emit()
