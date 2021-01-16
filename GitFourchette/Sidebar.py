from dataclasses import dataclass

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *

import git

from util import labelQuote


@dataclass
class SidebarEntry:
    type: str
    name: str

    def isRef(self):
        return self.type in ['localref', 'remoteref']

    def isLocalRef(self):
        return self.type == 'localref'

    def isTag(self):
        return self.type == 'tag'


# TODO: we should just use a custom model
def SidebarItem(name: str, data=None) -> QStandardItem:
    item = QStandardItem(name)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if data:
        item.setData(data, Qt.UserRole)
    return item


class Sidebar(QTreeView):
    refClicked = Signal(str)
    tagClicked = Signal(str)
    checkOutBranch = Signal(str)
    renameBranch = Signal(str, str)
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    deleteBranch = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setUniformRowHeights(True)
        self.setHeaderHidden(True)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)
        index = self.indexAt(localPoint)
        data: SidebarEntry = index.data(Qt.UserRole)
        if data.isLocalRef():
            menu = QMenu()

            if data.name != self.activeBranchName:
                menu.addAction(
                    F"Checkout {labelQuote(data.name)}",
                    lambda: self.checkOutBranch.emit(data.name))
                menu.addSeparator()
                menu.addAction(
                    F"Merge {labelQuote(data.name)} into {labelQuote(self.activeBranchName)}...",
                    lambda: self.mergeBranchIntoActive.emit(data.name))
                menu.addAction(
                    F"Rebase {labelQuote(self.activeBranchName)} onto {labelQuote(data.name)}...",
                    lambda: self.rebaseActiveOntoBranch.emit(data.name))

            menu.addSeparator()
            menu.addAction("Rename...", lambda: self._renameBranchFlow(data.name))
            menu.addAction("Delete...", lambda: self.deleteBranch.emit(data.name))

            menu.addSeparator()
            a = menu.addAction(F"Show In Graph")
            a.setCheckable(True)
            a.setChecked(True)

            menu.exec_(globalPoint)

    def _renameBranchFlow(self, oldName):
        dlg = QInputDialog(self)
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setWindowTitle("Rename Branch")
        dlg.setLabelText(F"Enter new name for branch {labelQuote(oldName)}:")
        dlg.setTextValue(oldName)
        dlg.setOkButtonText("Rename")
        rc = dlg.exec_()
        newName: str = dlg.textValue()
        dlg.deleteLater()  # avoid leaking dialog (can't use WA_DeleteOnClose because we needed to retrieve the message)
        if rc != QDialog.DialogCode.Accepted:
            return
        self.renameBranch.emit(oldName, newName)

    def fill(self, repo: git.Repo):
        model = QStandardItemModel()

        self.activeBranchName = repo.active_branch.name

        branchesParent = SidebarItem("Local Branches")
        for branch in repo.branches:
            caption = branch.name
            if repo.active_branch == branch:
                caption = F">{caption}<"
            item = SidebarItem(caption, SidebarEntry('localref', branch.name))
            branchesParent.appendRow(item)
        model.appendRow(branchesParent)

        remote: git.Remote
        for remote in repo.remotes:
            remoteParent = SidebarItem(F"Remote “{remote.name}”")
            remotePrefix = remote.name + '/'
            for ref in remote.refs:
                refShortName = ref.name
                if refShortName.startswith(remotePrefix):
                    refShortName = refShortName[len(remotePrefix):]
                item = SidebarItem(refShortName, SidebarEntry('remoteref', ref.name))
                remoteParent.appendRow(item)
            model.appendRow(remoteParent)

        tagsParent = QStandardItem("Tags")
        tag: git.Tag
        for tag in repo.tags:
            item = SidebarItem(tag.name, SidebarEntry('tag', tag.name))
            tagsParent.appendRow(item)
        model.appendRow(tagsParent)

        self._replaceModel(model)

        # expand branch container
        self.setExpanded(model.indexFromItem(branchesParent), True)

    def _replaceModel(self, model):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        self.setModel(model)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super().currentChanged(current, previous)
        if not current.isValid():
            return
        data = current.data(Qt.UserRole)
        if not data:
            return
        if data.isRef():
            self.refClicked.emit(data.name)
        elif data.isTag():
            self.tagClicked.emit(data.name)


