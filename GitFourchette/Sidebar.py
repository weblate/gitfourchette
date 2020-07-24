from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import git


class Sidebar(QTreeView):
    refClicked = Signal(str)
    tagClicked = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setUniformRowHeights(True)
        self.setHeaderHidden(True)

    def fill(self, repo: git.Repo):
        model = QStandardItemModel()

        branchesParent = QStandardItem("Local Branches")
        for branch in repo.branches:
            item = QStandardItem(branch.name)
            item.setData({'type': 'ref', 'name': branch.name }, Qt.UserRole)
            branchesParent.appendRow(item)
        model.appendRow(branchesParent)

        remote: git.Remote
        for remote in repo.remotes:
            remoteParent = QStandardItem(F"Remote “{remote.name}”")
            remotePrefix = remote.name + '/'
            for ref in remote.refs:
                refShortName = ref.name
                if refShortName.startswith(remotePrefix):
                    refShortName = refShortName[len(remotePrefix):]
                item = QStandardItem(refShortName)
                item.setData({'type': 'ref', 'name': ref.name}, Qt.UserRole)
                remoteParent.appendRow(item)
            model.appendRow(remoteParent)

        reff: git.Reference
        for reff in repo.refs:
            print(reff.name, reff.object)
            try:
                print("\tTAG:",reff.tag)
            except AttributeError:
                pass

        tagsParent = QStandardItem("Tags")
        tag: git.Tag
        for tag in repo.tags:
            item = QStandardItem(tag.name)
            item.setData({'type': 'tag', 'name': tag.name}, Qt.UserRole)
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
        if data['type'] == 'ref':
            self.refClicked.emit(data['name'])
        elif data['type'] == 'tag':
            self.tagClicked.emit(data['name'])


