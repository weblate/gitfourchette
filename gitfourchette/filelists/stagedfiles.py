from gitfourchette import settings
from gitfourchette.filelists.filelist import FileList
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.nav import NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.tasks import *


class StagedFiles(FileList):
    def __init__(self, parent):
        super().__init__(parent, NavContext.STAGED)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def createContextMenuActions(self, patches: list[Patch]) -> list[ActionDef]:
        actions = []

        n = len(patches)
        modeSet = set(patch.delta.new_file.mode for patch in patches)
        anySubmodules = FileMode.COMMIT in modeSet
        onlySubmodules = anySubmodules and len(modeSet) == 1

        if not anySubmodules:
            actions += [
                ActionDef(
                    self.tr("&Unstage %n Files", "", n),
                    self.unstage,
                    icon="git-unstage",
                    shortcuts=makeMultiShortcut(GlobalShortcuts.discardHotkeys),
                ),

                ActionDef(
                    self.tr("Stas&h Changes..."),
                    self.wantPartialStash,
                    shortcuts=TaskBook.shortcuts.get(NewStash, []),
                    icon="vcs-stash",
                ),

                self.revertModeActionDef(n, self.unstageModeChange),

                ActionDef.SEPARATOR,

                ActionDef(
                    self.tr("Open Diff in {0}").format(settings.getDiffToolName()),
                    self.wantOpenInDiffTool,
                    icon="vcs-diff",
                ),

                ActionDef(
                    self.tr("E&xport Diffs As Patch...", "", n),
                    self.savePatchAs,
                ),

                ActionDef.SEPARATOR,

                ActionDef(
                    self.tr("&Edit in {0}").format(settings.getExternalEditorName()),
                    self.openWorkdirFile,
                    icon="SP_FileIcon",
                ),

                ActionDef(
                    self.tr("Edit &HEAD Versions in {0}", "", n).format(settings.getExternalEditorName()),
                    self.openHeadRevision,
                ),
            ]

        elif onlySubmodules:
            actions += [
                ActionDef(
                    self.tr("%n Submodules", "please omit %n in singular form", n),
                    kind=ActionDef.Kind.Section,
                ),

                ActionDef(
                    self.tr("Unstage %n Submodules", "please omit %n in singular form", n),
                    self.unstage,
                ),

                ActionDef(
                    self.tr("Open %n Submodules in New Tabs", "please omit %n in singular form", n),
                    self.openSubmoduleTabs,
                ),
            ]

        else:
            actions += [
                ActionDef(self.tr("Selected files must be reviewed individually."), enabled=False)
            ]

        actions += super().createContextMenuActions(patches)
        return actions

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in GlobalShortcuts.stageHotkeys + GlobalShortcuts.discardHotkeys:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        patches = list(self.selectedPatches())
        UnstageFiles.invoke(self, patches)

    def unstageModeChange(self):
        patches = list(self.selectedPatches())
        UnstageModeChanges.invoke(self, patches)
