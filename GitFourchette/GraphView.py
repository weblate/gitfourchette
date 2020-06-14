from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import git
import html

from GraphDelegate import GraphDelegate
from Lanes import Lanes
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

    def fill(self, progress: QProgressDialog):
        repo = self.repoWidget.state.repo

        #model: QAbstractItemModel = self.model() ; model.clear()
        # Recreating a model on the fly is faster than clearing an existing one?
        model = QStandardItemModel(self)

        model.appendRow(QStandardItem("Uncommitted Changes"))
        commit: git.Commit
        laneGen = Lanes()
        i: int = 0
        for i, commit in enumerate(repo.iter_commits(repo.active_branch)):#, max_count=999000):
            if i != 0 and i % 1000 == 0:
                progress.setLabelText(F"{i:,} commits loaded.")
                QCoreApplication.processEvents()
            if progress.wasCanceled():
                raise Exception("Canceled!")

            # TODO: using commit.parents is very slow. We should do our own thing with git commands.
            meta = self.repoWidget.state.getOrCreateMetadata(commit)
            meta.lane, meta.laneData = laneGen.step(commit.binsha, [p.binsha for p in commit.parents])

            item = QStandardItem()
            item.setData(meta, Qt.DisplayRole)
            model.appendRow(item)

        progress.setLabelText(F"{i:,} commits total.")

        #progress.setCancelButton(None)
        #progress.setWindowFlags(progress.windowFlags() & ~Qt.WindowCloseButtonHint)
        #progress.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        QCoreApplication.processEvents()
        self._replaceModel(model)
        self.repaint()
        QCoreApplication.processEvents()
        self.onSetCurrent()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self.currentIndex().isValid():
            return
        commit: git.Commit = self.currentIndex().data().commit
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

        commit: git.Commit = current.data().commit

        # TODO: use a signal for this instead of touching changedFilesView directly
        cfv = self.repoWidget.changedFilesView
        cfv.clear()
        for parent in commit.parents:
            cfv.fillDiff(parent.diff(commit))
        cfv.selectFirstRow()
        self.repoWidget.filesStack.setCurrentIndex(0)
