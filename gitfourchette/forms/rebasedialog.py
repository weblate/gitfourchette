# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.forms.ui_rebasedialog import Ui_RebaseDialog
from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import TRebaseSequence, RebaseLineWrapper, RebaseOp, RebaseOpLetters, RebaseLine
from gitfourchette.rebase.rebasesequencedelegate import RebaseSequenceDelegate
from gitfourchette.toolbox import ActionDef, escamp


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
        assert self.view.uniformItemSizes()

        # Bind hotkeys
        legalKeys = set("abcdefghijklmnopqrstuvwxyz")
        for command in RebaseOp:
            hotkey = RebaseOpLetters[command]
            legalKeys.remove(hotkey)  # for debugging, raise KeyError if key assigned twice
            QShortcut(hotkey, self.view, lambda c=command: self.setCommandOnSelection(c), context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

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
        for item in self.iterateSelectedItems():
            item.op = command
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

        opHelp = {
            "pick"  : _("Use commit as-is"),
            "reword": _("Use commit, edit message"),
            "edit"  : _("Use commit, stop for amending"),
            "squash": _("Meld into previous commit, combine messages"),
            "fixup" : _("Meld into previous commit, keep previous message only"),
            "drop"  : _("Remove commit"),
        }

        actions = [
            ActionDef(
                op.capitalize() + " - " + escamp(opHelp[op]),
                lambda c=op: self.setCommandOnSelection(c),
                checkState=1 if op in selectedOps else -1,
                radioGroup="RebaseOpRadioGroup"
            )
            for op in RebaseOp
        ]

        menu = ActionDef.makeQMenu(self, actions)
        menu.setObjectName(self.objectName() + "ContextMenu")
        return menu

    def serializeSequence(self):
        text = "\n".join(str(i) for i in self.iterateAllItems())
        return text
