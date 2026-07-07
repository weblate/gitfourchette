# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette import trtables
from gitfourchette.forms.ui_rebasedialog import Ui_RebaseDialog
from gitfourchette.qt import *
from gitfourchette.rebase.rebaseliststyle import RebaseListStyle
from gitfourchette.rebase.rebasemenustyle import RebaseMenuStyle
from gitfourchette.rebase.rebasemodel import TRebaseSequence, RebaseLineWrapper, RebaseOp, RebaseOpColors, RebaseOpLetters, RebaseLine
from gitfourchette.rebase.rebasesequencedelegate import RebaseSequenceDelegate


SupportedRebaseOps = {
    RebaseOp.Pick,
    RebaseOp.Reword,
    RebaseOp.Edit,
    # RebaseOp.Squash,  # TODO - need message edit support
    RebaseOp.Fixup,
    RebaseOp.Drop,
}


class RebaseDialog(QDialog):
    @property
    def view(self):
        return self.ui.commitList

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)
        self.ui = Ui_RebaseDialog()
        self.ui.setupUi(self)
        self.view.customContextMenuRequested.connect(self.onContextMenuRequested)
        self.view.setItemDelegate(RebaseSequenceDelegate(self.view))
        self.view.setEditTriggers(QListView.EditTrigger.DoubleClicked | QListView.EditTrigger.EditKeyPressed)
        assert self.view.uniformItemSizes()

        self.view.setStyle(RebaseListStyle())

        # Bind hotkeys
        for op, hotkey in RebaseOpLetters.items():
            if op not in SupportedRebaseOps:
                continue
            QShortcut(hotkey, self.view, lambda c=op: self.setCommandOnSelection(c), context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def setSequence(self, sequence: TRebaseSequence):
        self.view.clear()
        for item in sequence:
            self.view.addItem(RebaseLineWrapper(item))

    def iterateSelectedItems(self):
        for wrapper in self.view.selectedItems():
            item = wrapper.item
            assert isinstance(item, RebaseLine)
            yield item

    def iterateAllItems(self):
        for row in range(self.view.count()):
            wrapper = self.view.item(row)
            item = wrapper.item
            assert isinstance(item, RebaseLine)
            yield item

    def setCommandOnSelection(self, command: RebaseOp):
        assert command in SupportedRebaseOps, f"rebase op '{command}' not supported yet"

        for wrapper in self.view.selectedItems():
            assert isinstance(wrapper, RebaseLineWrapper)

            item = wrapper.item
            item.op = command

            wrapper.updateFlags()  # flip editable flag if rewording

        self.view.viewport().update()

    def onContextMenuRequested(self, point: QPoint):
        menu = self.makeContextMenu()
        if menu is not None:
            menu.aboutToHide.connect(menu.deleteLater)
            menu.popup(self.mapToGlobal(point))

    def makeContextMenu(self):
        selectedOps = {item.op for item in self.iterateSelectedItems()}
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
        text = "\n".join(str(i) for i in self.iterateAllItems())
        return text
