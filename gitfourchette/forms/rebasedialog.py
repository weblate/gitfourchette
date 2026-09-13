# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette import trtables
from gitfourchette.forms.ui_rebasedialog import Ui_RebaseDialog
from gitfourchette.localization import *
from gitfourchette.nav import NavLocator
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import RebaseOp, RebaseOpColors, RebaseOpLetters, SupportedRebaseOps, TRebaseSequence
from gitfourchette.rebase.rebasesequencemodel import RebaseSequenceModel
from gitfourchette.toolbox import asyncMessageBox, QRichTextMenu


class RebaseDialog(QDialog):
    LastGeometry = b""

    exploreCommit = Signal(NavLocator)

    initialSequence: TRebaseSequence

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        self.initialSequence = []

        self.ui = Ui_RebaseDialog()
        self.ui.setupUi(self)

        # When data changes, flag the sequence as modified so that reject() asks
        # for confirmation before closing.
        self.ui.sequence.sequenceModel.rowsMoved.connect(lambda: self.setWindowModified(True))
        self.ui.sequence.sequenceModel.dataChanged.connect(lambda: self.setWindowModified(True))

        self.ui.sequence.customContextMenuRequested.connect(self.onContextMenuRequested)
        self.ui.sequence.opShortcut.connect(self.setCommandOnSelection)

        # Restore window geometry (TODO: On GNOME, is issue #50 still relevant?)
        if not GNOME and RebaseDialog.LastGeometry:
            self.restoreGeometry(RebaseDialog.LastGeometry)

        self.finished.connect(self._onFinishedSaveGeometry)

        self.ui.sequence.commitSelected.connect(lambda oid: self.exploreCommit.emit(NavLocator.inCommit(oid)))

    def _onFinishedSaveGeometry(self):
        RebaseDialog.LastGeometry = self.saveGeometry().data()

    def reject(self):
        if not self.isWindowModified():
            super().reject()
            return

        def qmbFinished(result: int):
            if result == QMessageBox.StandardButton.Close:
                self.setWindowModified(False)
                self.reject()

        qmb = asyncMessageBox(
            self,
            "question",
            _p("RebaseDialog", "Rebase"),
            _("Really close this rebase plan? It won’t be saved."),
            QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel,
        )
        qmb.finished.connect(qmbFinished)
        qmb.show()

    def setSequence(self, sequence: TRebaseSequence):
        self.initialSequence = [line.copy() for line in sequence]

        self.ui.sequence.sequenceModel.setSequence(self.initialSequence)

    def setCommandOnSelection(self, command: RebaseOp):
        assert command in SupportedRebaseOps, f"rebase op '{command}' not supported yet"

        indexes = self.ui.sequence.selectedIndexes()

        if not indexes:
            QApplication.beep()
            return

        for index in indexes:
            line = index.data(RebaseSequenceModel.RebaseLineRole)
            line.op = command

        self.ui.sequence.sequenceModel.emitUserDataChanged(indexes)
        self.ui.sequence.viewport().update()

        # Spawn QLineEdit immediately if rewording
        if command.isEditable():
            self.ui.sequence.edit(indexes[0])

    def onContextMenuRequested(self, point: QPoint):
        menu = self.makeContextMenu()
        if menu is not None:
            menu.aboutToHide.connect(menu.deleteLater)
            menu.popup(self.mapToGlobal(point))

    def makeContextMenu(self):
        selectedLines = self.ui.sequence.selectedRebaseLines()
        selectedOps = {item.op for item in selectedLines}
        if not selectedOps:
            return None

        menu = QRichTextMenu(self)
        actionGroup = QActionGroup(menu)
        actionGroup.setExclusionPolicy(QActionGroup.ExclusionPolicy.Exclusive)

        for op in RebaseOp:
            if op not in SupportedRebaseOps:
                continue

            opColor = RebaseOpColors[op]
            opName = op.capitalize()
            opAccel = RebaseOpLetters.get(op, "")
            opHelp = trtables.enum(op)

            richLabel = f"<span style='color: {opColor.name()}; font-weight: bold;'>{opName}{_(':')}</span> {opHelp}"

            action = menu.addRichTextAction(richLabel, opAccel)
            action.setCheckable(True)
            action.setChecked(op in selectedOps)
            action.setActionGroup(actionGroup)
            action.triggered.connect(lambda _checked, c=op: self.setCommandOnSelection(c))
            menu.addAction(action)

        return menu

    def serializeSequence(self):
        text = "\n".join(str(i) for i in self.ui.sequence.effectiveSequence())
        return text
