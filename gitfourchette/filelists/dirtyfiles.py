from gitfourchette import settings
from gitfourchette.filelists.filelist import FileList
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.nav import NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.tasks import *


class DirtyFiles(FileList):
    def __init__(self, parent):
        super().__init__(parent, NavContext.UNSTAGED)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def createContextMenuActions(self, patches: list[Patch]) -> list[ActionDef]:
        actions = []

        n = len(patches)

        statusSet = set(patch.delta.status for patch in patches)

        if DeltaStatus.CONFLICTED not in statusSet:
            actions += [
                ActionDef(
                    self.tr("&Stage %n File(s)", "", n),
                    self.stage,
                    icon="list-add",  # QStyle.StandardPixmap.SP_ArrowDown,
                    shortcuts=makeMultiShortcut(GlobalShortcuts.stageHotkeys),
                ),

                ActionDef(
                    self.tr("&Discard Changes"),
                    self.discard,
                    icon=QStyle.StandardPixmap.SP_TrashIcon,
                    shortcuts=makeMultiShortcut(GlobalShortcuts.discardHotkeys),
                ),

                ActionDef(
                    self.tr("Stas&h Changes..."),
                    self.wantPartialStash,
                    icon="vcs-stash",
                    shortcuts=TaskBook.shortcuts.get(NewStash, [])
                ),

                self.revertModeActionDef(n, self.discardModeChanges),

                ActionDef.SEPARATOR,

                ActionDef(
                    self.tr("Compare in {0}").format(settings.getDiffToolName()),
                    self.wantOpenInDiffTool,
                    icon="vcs-diff",
                ),

                ActionDef(
                    self.tr("E&xport Diff(s) As Patch...", "", n),
                    self.savePatchAs
                ),
            ]
        elif len(statusSet) == 1:  # Only conflicted files
            actions += [
                ActionDef(
                    self.tr("%n Merge Conflicts", "singular form should simply say 'Merge Conflict'", n),
                    isSection=True,
                ),

                ActionDef(
                    self.tr("Resolve by Accepting “Theirs”"),
                    self.mergeTakeTheirs,
                ),

                ActionDef(
                    self.tr("Resolve by Keeping “Ours”"),
                    self.mergeKeepOurs,
                ),

                # ActionDef(
                #     self.tr("Merge in {0}").format(settings.getMergeToolName()),
                #     self.mergeInTool,
                # )
            ]
        else:
            # Conflicted + non-conflicted files selected
            actions += [
                ActionDef(
                    self.tr("Mixed conflicts"),
                    isSection=True,
                ),
                ActionDef(
                    self.tr("Selected files must be reviewed individually."),
                    enabled=False,
                ),
            ]

        if actions:
            actions.append(ActionDef.SEPARATOR)

        actions += [
            ActionDef(
                self.tr("&Edit in {0}", "", n).format(settings.getExternalEditorName()),
                self.openWorkdirFile,
                icon=QStyle.StandardPixmap.SP_FileIcon,
            ),

            ActionDef(
                self.tr("Edit HEAD Version(s) in {0}", "", n).format(settings.getExternalEditorName()),
                self.openHeadRevision,
            ),

            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("Open &Folder(s)", "", n),
                self.showInFolder,
                icon=QStyle.StandardPixmap.SP_DirIcon,
            ),

            ActionDef(
                self.tr("&Copy Path(s)", "", n),
                self.copyPaths,
                shortcuts=GlobalShortcuts.copy,
            ),

            self.pathDisplayStyleSubmenu()
        ]

        return actions

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in GlobalShortcuts.stageHotkeys:
            self.stage()
        elif k in GlobalShortcuts.discardHotkeys:
            self.discard()
        else:
            super().keyPressEvent(event)

    def stage(self):
        patches = list(self.selectedPatches())
        StageFiles.invoke(self, patches)

    def discard(self):
        patches = list(self.selectedPatches())
        DiscardFiles.invoke(self, patches)

    def discardModeChanges(self):
        patches = list(self.selectedPatches())
        DiscardModeChanges.invoke(self, patches)

    def _mergeKeep(self, keepOurs: bool):
        patches = list(self.selectedPatches())

        conflicts = self.repo.index.conflicts

        table = {}

        for patch in patches:
            path = patch.delta.new_file.path
            ancestor, ours, theirs = conflicts[path]
            if not ours and not theirs:  # special treatment for DELETED_BY_BOTH
                table[path] = NULL_OID
            elif keepOurs:
                table[path] = ours.id
            else:
                table[path] = theirs.id

        HardSolveConflicts.invoke(self, table)

    def mergeKeepOurs(self):
        self._mergeKeep(keepOurs=True)

    def mergeTakeTheirs(self):
        self._mergeKeep(keepOurs=False)
