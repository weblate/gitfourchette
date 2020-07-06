from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import git
import html

from GraphDelegate import GraphDelegate
import settings
from util import messageSummary, fplural


class GraphView(QListView):
    uncommittedChangesClicked = Signal()
    emptyClicked = Signal()
    commitClicked = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)  # sinon on peut double-cliquer pour éditer les lignes...
        self.setItemDelegate(GraphDelegate(parent, parent=self))

        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        getInfoAction = QAction("Get Info...", self)
        getInfoAction.triggered.connect(self.getInfoOnCurrentCommit)
        self.addAction(getInfoAction)

    def _replaceModel(self, model):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        self.setModel(model)

    def fill(self, orderedCommitMetadata):
        model = QStandardItemModel(self)  # creating a model from scratch seems faster than clearing an existing one
        model.appendRow(QStandardItem())
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
        self.getInfoOnCurrentCommit()

    def getInfoOnCurrentCommit(self):
        if not self.currentIndex().isValid():
            return

        repo: git.Repo = self.repoWidget.state.repo
        commit: git.Commit = repo.commit(self.currentIndex().data().hexsha)

        summary, contd = messageSummary(commit.message)

        postSummary = ""
        nLines = len(commit.message.rstrip().split('\n'))
        if contd:
            postSummary = F"<br>\u25bc <i>click &ldquo;Show Details&rdquo; to reveal full message " \
                  F"({nLines} lines)</i>"

        parentHashes = [p.hexsha[:settings.prefs.shortHashChars] for p in commit.parents]
        parentLabelMarkup = html.escape(fplural('# Parent^s', len(parentHashes)))
        parentValueMarkup = html.escape(', '.join(parentHashes))

        authorMarkup = F"{html.escape(commit.author.name)} &lt;{html.escape(commit.author.email)}&gt;" \
            F"<br>{html.escape(commit.authored_datetime.strftime(settings.prefs.longTimeFormat))}"

        if (commit.author.email == commit.committer.email
                and commit.author.name == commit.committer.name
                and commit.authored_datetime == commit.committed_datetime):
            committerMarkup = F"<i>(same as author)</i>"
        else:
            committerMarkup = F"{html.escape(commit.committer.name)} &lt;{html.escape(commit.committer.email)}&gt;" \
                F"<br>{html.escape(commit.committed_datetime.strftime(settings.prefs.longTimeFormat))}"

        markup = F"""<span style='font-size: large'>{summary}</span>{postSummary}
            <br>
            <table>
            <tr><td><b>Full Hash </b></td><td>{commit.hexsha}</td></tr>
            <tr><td><b>{parentLabelMarkup} </b></td><td>{parentValueMarkup}</td></tr>
            <tr><td><b>Author </b></td><td>{authorMarkup}</td></tr>
            <tr><td><b>Committer </b></td><td>{committerMarkup}</td></tr>
            </table>"""
        messageBox = QMessageBox(
            QMessageBox.Information,
            F"Commit info {commit.hexsha[:settings.prefs.shortHashChars]}",
            markup,
            parent=self)
        if contd:
            messageBox.setDetailedText(commit.message)
        messageBox.exec_()

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        # do standard callback, such as scrolling the viewport if reaching the edges, etc.
        super().selectionChanged(selected, deselected)

        if len(selected.indexes()) == 0:
            self.onSetCurrent(None)
        else:
            self.onSetCurrent(selected.indexes()[0])

    def onSetCurrent(self, current=None):
        if current is None or not current.isValid():
            self.emptyClicked.emit()
        elif current.row() == 0:  # uncommitted changes
            self.uncommittedChangesClicked.emit()
        else:
            self.commitClicked.emit(current.data().hexsha)
