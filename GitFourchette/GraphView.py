from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import git
import html

from GraphDelegate import GraphDelegate
import settings


class GraphView(QListView):
    def __init__(self, parent):
        super().__init__(parent)
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)  # sinon on peut double-cliquer pour éditer les lignes...
        self.setItemDelegate(GraphDelegate())

    def _replaceModel(self, model):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        self.setModel(model)

    def fill(self, orderedCommitMetadata):
        model = QStandardItemModel(self)  # creating a model from scratch seems faster than clearing an existing one
        model.appendRow(QStandardItem("Uncommitted Changes"))
        model.insertRows(1, len(orderedCommitMetadata))
        for i, meta in enumerate(orderedCommitMetadata):
            model.setData(model.index(1 + i, 0), meta, Qt.DisplayRole)
        self._replaceModel(model)
        self.onSetCurrent()

    def patchFill(self, trimStartRows, orderedCommitMetadata):
        model = self.model()
        model.removeRows(1, trimStartRows)
        model.insertRows(1, len(orderedCommitMetadata))
        for i, meta in enumerate(orderedCommitMetadata):
            model.setData(model.index(1 + i, 0), meta, Qt.DisplayRole)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self.currentIndex().isValid():
            return
        repo: git.Repo = self.repoWidget.state.repo
        commit: git.Commit = self.currentIndex().data().commit(repo)
        QMessageBox.about(None, F"Commit info {commit.hexsha[:7]}", F"""<h2>Commit info</h2>
<b>SHA</b><br>
{commit.hexsha}
<br><br>
<b>Author</b><br>
{html.escape(commit.author.name)} &lt;{html.escape(commit.author.email)}&gt;
<br>{html.escape(commit.authored_datetime.strftime(settings.prefs.longTimeFormat))}
<br><br>
<b>Committer</b><br>
{html.escape(commit.committer.name)} &lt;{html.escape(commit.committer.email)}&gt;
<br>{html.escape(commit.committed_datetime.strftime(settings.prefs.longTimeFormat))}
<br><br>
<b>Message</b><br>
{html.escape(commit.message)}""")

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        # do standard callback, such as scrolling the viewport if reaching the edges, etc.
        super().selectionChanged(selected, deselected)

        if len(selected.indexes()) == 0:
            self.onSetCurrent(None)
        else:
            self.onSetCurrent(selected.indexes()[0])

    def onSetCurrent(self, current=None):
        # if current is None:
        #     current = self.currentIndex()

        if current is None or not current.isValid():
            self.repoWidget.setNoCommitSelected()
            return

        if current.row() == 0:  # uncommitted changes
            self.repoWidget.fillStageView()
            return

        repo: git.Repo = self.repoWidget.state.repo
        commit: git.Commit = current.data().commit(repo)

        # TODO: use a signal for this instead of touching changedFilesView directly
        cfv = self.repoWidget.changedFilesView
        cfv.clear()
        for parent in commit.parents:
            cfv.fillDiff(parent.diff(commit))
        cfv.selectFirstRow()
        self.repoWidget.filesStack.setCurrentIndex(0)
