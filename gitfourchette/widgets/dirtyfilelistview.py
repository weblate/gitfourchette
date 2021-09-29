from allqt import *
from filelistentry import FileListEntry
from widgets.filelistview import FileListView
from stagingstate import StagingState
from util import ActionDef
import os
import pygit2
import settings
import trash


class DirtyFileListView(FileListView):
    patchApplied: Signal = Signal()

    def __init__(self, parent):
        super().__init__(parent, StagingState.UNSTAGED)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def createContextMenuActions(self):
        return [
            ActionDef("&Stage", self.stage, QStyle.SP_ArrowDown),
            ActionDef("&Discard Changes", self.discard, QStyle.SP_TrashIcon),
            None,
            ActionDef("&Open File in External Editor", self.openFile),
        ] + super().createContextMenuActions()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            self.stage()
        elif k in settings.KEYS_REJECT:
            self.discard()
        else:
            super().keyPressEvent(event)

    def addUntrackedFileEntries(self, untracked: list[str]):
        for path in untracked:
            self.addEntry(FileListEntry.Untracked(path))

    # Context menu action
    def stage(self):
        index = self.repo.index
        for entry in self.selectedEntries():
            if entry.patch.delta.status == pygit2.GIT_DELTA_DELETED:
                index.remove(entry.path)
            else:
                index.add(entry.path)
        index.write()
        self.patchApplied.emit()

    # Context menu action
    def discard(self):
        entries = list(self.selectedEntries())

        if len(entries) == 1:
            question = F"Really discard changes to {entries[0].path}?"
        else:
            question = F"Really discard changes to {len(entries)} files?"

        qmb = QMessageBox(
            QMessageBox.Question,
            "Discard changes",
            F"{question}\nThis cannot be undone!",
            QMessageBox.Discard | QMessageBox.Cancel,
            self)
        yes = qmb.button(QMessageBox.Discard)
        yes.setText("Discard changes")
        qmb.exec_()
        if qmb.clickedButton() != yes:
            return

        # TODO: Trash multiple files at once
        for entry in entries:
            if entry.diff is not None:  # tracked file
                trash.trashGitDiff(self.repo, entry.diff)
                self.git.restore(entry.path)  # self.diff.a_path)
            else:  # untracked file
                trash.trashUntracked(self.repo, entry.path)
                os.remove(os.path.join(self.repo.workdir, entry.path))
        self.patchApplied.emit()


