from gitfourchette import settings
from gitfourchette.filelists.filelist import FileList
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.nav import NavContext
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class StagedFiles(FileList):
    unstageFiles: Signal = Signal(list)
    unstageModeChanges: Signal = Signal(list)

    def __init__(self, parent):
        super().__init__(parent, NavContext.STAGED)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def createContextMenuActions(self, n):
        return [
            ActionDef(
                self.tr("&Unstage %n File(s)", "", n),
                self.unstage,
                QStyle.StandardPixmap.SP_ArrowUp,
                shortcuts=GlobalShortcuts.discardHotkeys,
            ),

            ActionDef(
                self.tr("Stas&h Changes..."),
                self.wantPartialStash,
                shortcuts=GlobalShortcuts.newStash,
                icon="vcs-stash",
            ),

            self.revertModeActionDef(n, self.wantUnstageModeChange),

            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("Open &Diff(s) in {0}", "", n).format(settings.getDiffToolName()),
                self.wantOpenInDiffTool,
                icon="vcs-diff",
            ),

            ActionDef(
                self.tr("E&xport Diff(s) As Patch...", "", n),
                self.savePatchAs,
            ),

            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("&Open in {0}").format(settings.getExternalEditorName()),
                self.openWorkdirFile,
                icon=QStyle.StandardPixmap.SP_FileIcon,
            ),

            ActionDef(
                self.tr("Open &HEAD Version(s) in {0}", "", n).format(settings.getExternalEditorName()),
                self.openHeadRevision,
            ),

            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("Open &Path(s)", "", n),
                self.showInFolder,
                icon=QStyle.StandardPixmap.SP_DirIcon,
            ),

            ActionDef(
                self.tr("&Copy Path(s)", "", n),
                self.copyPaths,
                shortcuts=GlobalShortcuts.copy
            ),

            self.pathDisplayStyleSubmenu(),
        ] + super().createContextMenuActions(n)

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in GlobalShortcuts.stageHotkeys + GlobalShortcuts.discardHotkeys:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        self.unstageFiles.emit(list(self.selectedEntries()))

    def wantUnstageModeChange(self):
        self.unstageModeChanges.emit(list(self.selectedEntries()))


