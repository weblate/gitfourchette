# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette import trtables
from gitfourchette.forms.ui_rebasedialog import Ui_RebaseDialog
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import TRebaseSequence, RebaseLineWrapper, RebaseOp, RebaseOpColors, RebaseOpLetters, SupportedRebaseOps
from gitfourchette.toolbox import asyncMessageBox, QRichTextMenu
from gitfourchette.localization import *


class RebaseDialog(QDialog):
    LastGeometry = b""

    initialSequence: TRebaseSequence

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        self.initialSequence = []

        self.ui = Ui_RebaseDialog()
        self.ui.setupUi(self)
        self.ui.sequence.customContextMenuRequested.connect(self.onContextMenuRequested)
        self.ui.sequence.opShortcut.connect(self.setCommandOnSelection)

        # When data changes, flag the sequence as modified so that reject() asks
        # for confirmation before closing.
        listModel = self.ui.sequence.model()
        listModel.rowsMoved.connect(lambda: self.setWindowModified(True))
        listModel.dataChanged.connect(lambda: self.setWindowModified(True))

        # Restore window geometry (TODO: On GNOME, is issue #50 still relevant?)
        if not GNOME and RebaseDialog.LastGeometry:
            self.restoreGeometry(RebaseDialog.LastGeometry)

        self.finished.connect(self._onFinishedSaveGeometry)

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

        self.ui.sequence.clear()
        for line in self.initialSequence:
            lineWrapper = RebaseLineWrapper(line)
            self.ui.sequence.addItem(lineWrapper)

    def setCommandOnSelection(self, command: RebaseOp):
        assert command in SupportedRebaseOps, f"rebase op '{command}' not supported yet"

        selectedItems = self.ui.sequence.selectedItems()

        for wrapper in selectedItems:
            assert isinstance(wrapper, RebaseLineWrapper)

            item = wrapper.item
            item.op = command

            wrapper.updateFlags()  # flip editable flag if rewording

        # Spawn QLineEdit immediately if rewording
        if command.isEditable() and selectedItems:
            self.ui.sequence.editItem(selectedItems[0])

        self.ui.sequence.viewport().update()

    def onContextMenuRequested(self, point: QPoint):
        menu = self.makeContextMenu()
        if menu is not None:
            menu.aboutToHide.connect(menu.deleteLater)
            menu.popup(self.mapToGlobal(point))

    def makeContextMenu(self):
        selectedOps = {item.op for item in self.ui.sequence.selectedRebaseLines()}
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
        text = "\n".join(str(i) for i in self.ui.sequence.allRebaseLines())
        return text
