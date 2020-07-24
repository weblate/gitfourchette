from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import git


class Sidebar(QTreeView):
    branchClicked = Signal(str)

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
            item.setData({
                'type': 'branch',
                'name': branch.name
            }, Qt.UserRole)
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
                remoteParent.appendRow(item)
            model.appendRow(remoteParent)

        tagsParent = QStandardItem("Tags")
        tag: git.Tag
        for tag in repo.tags:
            item = QStandardItem(tag.name)
            tagsParent.appendRow(item)
        model.appendRow(tagsParent)

        self._replaceModel(model)

        # expand branch container
        self.setExpanded(model.indexFromItem(branchesParent), True)

    def _replaceModel(self, model):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        self.setModel(model)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        # do standard callback, such as scrolling the viewport if reaching the edges, etc.
        super().selectionChanged(selected, deselected)
        if len(selected.indexes()) == 0:
            return
        i0 : QModelIndex = selected.indexes()[0]
        data = i0.data(Qt.UserRole)
        if not data:
            return
        if data['type'] == 'branch':
            self.branchClicked.emit(data['name'])


