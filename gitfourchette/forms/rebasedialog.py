# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette import trtables
from gitfourchette.forms.ui_rebasedialog import Ui_RebaseDialog
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemenustyle import RebaseMenuStyle
from gitfourchette.rebase.rebasemodel import TRebaseSequence, RebaseLineWrapper, RebaseOp, RebaseOpColors, RebaseOpLetters


SupportedRebaseOps = {
    RebaseOp.Pick,
    RebaseOp.Reword,
    RebaseOp.Edit,
    # RebaseOp.Squash,  # TODO - need message edit support
    RebaseOp.Fixup,
    RebaseOp.Drop,
}


class RebaseDialog(QDialog):
    def __init__(self, parent: QWidget | None):
        super().__init__(parent)
        self.ui = Ui_RebaseDialog()
        self.ui.setupUi(self)
        self.ui.sequence.customContextMenuRequested.connect(self.onContextMenuRequested)

        # Bind hotkeys
        for op, hotkey in RebaseOpLetters.items():
            if op not in SupportedRebaseOps:
                continue
            QShortcut(hotkey, self.ui.sequence, lambda c=op: self.setCommandOnSelection(c), context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def setSequence(self, sequence: TRebaseSequence):
        self.ui.sequence.clear()
        for item in sequence:
            self.ui.sequence.addItem(RebaseLineWrapper(item))

    def setCommandOnSelection(self, command: RebaseOp):
        assert command in SupportedRebaseOps, f"rebase op '{command}' not supported yet"

        for wrapper in self.ui.sequence.selectedItems():
            assert isinstance(wrapper, RebaseLineWrapper)

            item = wrapper.item
            item.op = command

            wrapper.updateFlags()  # flip editable flag if rewording

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

        proxy = RebaseMenuStyle()
        menu = QMenu(self)
        menu.setStyle(proxy)
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
            plainLabel = proxy.prepareRichLabel(richLabel, accelerator=opAccel)

            action = QAction(menu)
            action.setText(plainLabel)
            action.setCheckable(True)
            action.setChecked(op in selectedOps)
            action.setActionGroup(actionGroup)
            action.triggered.connect(lambda _checked, c=op: self.setCommandOnSelection(c))
            menu.addAction(action)

        return menu

    def serializeSequence(self):
        text = "\n".join(str(i) for i in self.ui.sequence.allRebaseLines())
        return text
