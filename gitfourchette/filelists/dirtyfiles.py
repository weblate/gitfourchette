# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

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

    def contextMenuActions(self, patches: list[Patch]) -> list[ActionDef]:
        actions = []

        n = len(patches)

        statusSet = {patch.delta.status for patch in patches}
        modeSet = {patch.delta.new_file.mode for patch in patches}

        anyConflicts = DeltaStatus.CONFLICTED in statusSet
        anySubmodules = FileMode.COMMIT in modeSet
        onlyConflicts = anyConflicts and len(statusSet) == 1
        onlySubmodules = anySubmodules and len(modeSet) == 1

        if not anyConflicts and not anySubmodules:
            contextMenuActionStage = ActionDef(
                self.tr("&Stage %n Files", "", n),
                self.stage,
                icon="git-stage",
                shortcuts=GlobalShortcuts.stageHotkeys[0])

            contextMenuActionDiscard = ActionDef(
                self.tr("&Discard Changes"),
                self.discard,
                icon="git-discard",
                shortcuts=GlobalShortcuts.discardHotkeys[0])

            actions += [
                contextMenuActionStage,
                contextMenuActionDiscard,
                self.contextMenuActionStash(),
                self.contextMenuActionRevertMode(patches, self.discardModeChanges),
                ActionDef.SEPARATOR,
                *self.contextMenuActionsDiff(patches),
            ]

        elif onlyConflicts:
            actions += [
                ActionDef(
                    self.tr("%n Merge Conflicts", "singular form should simply say 'Merge Conflict' without the %n", n),
                    kind=ActionDef.Kind.Section,
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

        elif onlySubmodules:
            actions += [
                ActionDef(
                    self.tr("%n Submodules", "please omit %n in singular form", n),
                    kind=ActionDef.Kind.Section,
                ),
                ActionDef(
                    self.tr("Stage %n Submodules", "please omit %n in singular form", n),
                    self.stage,
                ),
                ActionDef(
                    self.tr("Discard Changes in %n Submodules", "please omit %n in singular form", n),
                    self.discard,
                ),
                ActionDef(
                    self.tr("Open %n Submodules in New Tabs", "please omit %n in singular form", n),
                    self.openSubmoduleTabs,
                ),
            ]

        else:
            # Conflicted + non-conflicted files selected
            # or Submodules + non-submodules selected
            actions += [
                ActionDef(self.tr("Selected files must be reviewed individually."), enabled=False),
            ]

        if actions:
            actions.append(ActionDef.SEPARATOR)

        if not onlySubmodules:
            actions += [
                *self.contextMenuActionsEdit(patches),
                ActionDef.SEPARATOR,
            ]

        actions += super().contextMenuActions(patches)
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

            keepEntry = ours if keepOurs else theirs
            keepId = keepEntry.id if keepEntry is not None else NULL_OID
            table[path] = keepId

        HardSolveConflicts.invoke(self, table)

    def mergeKeepOurs(self):
        self._mergeKeep(keepOurs=True)

    def mergeTakeTheirs(self):
        self._mergeKeep(keepOurs=False)

    def onSpecialMouseClick(self):
        if settings.prefs.middleClickToStage:
            self.stage()
