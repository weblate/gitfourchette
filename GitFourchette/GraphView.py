from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import git
import html
import datetime

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
        repo: git.Repo = self.repoWidget.state.repo

        #model: QAbstractItemModel = self.model() ; model.clear()
        # Recreating a model on the fly is faster than clearing an existing one?
        model = QStandardItemModel(self)

        model.appendRow(QStandardItem("Uncommitted Changes"))
        laneGen = Lanes()
        i: int = 0

        boldCommitHash = repo.active_branch.commit.hexsha
        self.repoWidget.state.getOrCreateMetadata(boldCommitHash).bold = True

        progress.setLabelText("Talking to git...")
        QCoreApplication.processEvents()
        timeA = datetime.datetime.now()
        output = repo.git.log(topo_order=True, all=True, pretty='tformat:%x00%H%n%P%n%an%n%ae%n%at%n%B')
        split = output.split('\x00')
        del split[0]
        split[-1] += '\n'
        commitCount = len(split)
        progress.setMaximum(commitCount)

        timeB = datetime.datetime.now()

        progress.setLabelText(F"Processing {commitCount:,} commits.")

        for i, commitData in enumerate(split):
            if i % 10000 == 0:
                #progress.setLabelText(F"Processing commit {i:,} of {commitCount:,}")
                progress.setValue(i)
                QCoreApplication.processEvents()
            if progress.wasCanceled():
                print("aborted")
                QMessageBox.warning(self, "Loading aborted", F"Loading aborted.\nHistory will be truncated to {i:,} commits.")
                break

            hash, parentHashes, author, authorEmail, authorDate, body = commitData.split('\n', 5)

            meta = self.repoWidget.state.getOrCreateMetadata(hash)
            meta.author = author
            meta.authorEmail = authorEmail
            meta.authorTimestamp = int(authorDate)
            meta.body = body

            # compute lanes
            meta.lane, meta.laneData = laneGen.step(hash, parentHashes.split())

            item = QStandardItem()
            item.setData(meta, Qt.DisplayRole)
            model.appendRow(item)

        timeC = datetime.datetime.now()

        print(int((timeC - timeB).total_seconds() * 1000), int((timeB - timeA).total_seconds() * 1000))

        progress.setLabelText(F"{i:,} commits total.")
        progress.setValue(commitCount)

        QCoreApplication.processEvents()
        import pickle
        with open(F'/tmp/gitfourchette-{settings.history.getRepoNickname(repo.working_tree_dir)}.pickle', 'wb') as handle:
            pickle.dump(self.repoWidget.state.commitMetadata, handle, protocol=pickle.HIGHEST_PROTOCOL)

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
