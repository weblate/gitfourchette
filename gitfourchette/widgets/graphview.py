from allqt import *
from graphdelegate import GraphDelegate
from repostate import CommitMetadata
from util import messageSummary, fplural, shortHash, textInputDialog
import git
import html
import settings


class GraphView(QListView):
    uncommittedChangesClicked = Signal()
    emptyClicked = Signal()
    commitClicked = Signal(str)
    newBranchFromCommit = Signal(str, str)

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
        checkoutAction = QAction("Check Out...", self)
        checkoutAction.triggered.connect(self.checkoutCurrentCommit)
        self.addAction(checkoutAction)
        cherrypickAction = QAction("Cherry Pick...", self)
        cherrypickAction.triggered.connect(self.cherrypickCurrentCommit)
        self.addAction(cherrypickAction)
        branchAction = QAction("Start Branch from Here...", self)
        branchAction.triggered.connect(self.branchFromCurrentCommit)
        self.addAction(branchAction)

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

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            self.getInfoOnCurrentCommit()
        else:
            super().keyPressEvent(event)

    @property
    def repo(self) -> git.Repo:
        return self.repoWidget.state.repo

    @property
    def currentCommitHash(self):
        if not self.currentIndex().isValid():
            return
        data : CommitMetadata = self.currentIndex().data()
        if not data:  # Uncommitted Changes has no bound data
            return
        return data.hexsha

    def getInfoOnCurrentCommit(self):
        commitHash = self.currentCommitHash
        if not commitHash:
            return

        # TODO: we should probably run this as a worker; simply adding "with self.repoWidget.state.mutexLocker()" blocks the UI thread ... which also blocks the worker in the background! Is the qthreadpool given "time to breathe" by the GUI thread?

        commit: git.Commit = self.repo.commit(commitHash)
        data: CommitMetadata = self.currentIndex().data()

        summary, contd = messageSummary(commit.message)

        postSummary = ""
        nLines = len(commit.message.rstrip().split('\n'))
        if contd:
            postSummary = F"<br>\u25bc <i>click &ldquo;Show Details&rdquo; to reveal full message " \
                  F"({nLines} lines)</i>"

        parentHashes = [shortHash(p.hexsha) for p in commit.parents]
        parentLabelMarkup = html.escape(fplural('# Parent^s', len(parentHashes)))
        parentValueMarkup = html.escape(', '.join(parentHashes))

        childHashes = [shortHash(c) for c in data.childHashes]
        childLabelMarkup = html.escape(fplural('# Child^ren', len(childHashes)))
        childValueMarkup = html.escape(', '.join(childHashes))

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
            <tr><td><b>{childLabelMarkup} </b></td><td>{childValueMarkup}</td></tr>
            <tr><td><b>Author </b></td><td>{authorMarkup}</td></tr>
            <tr><td><b>Committer </b></td><td>{committerMarkup}</td></tr>
            <tr><td><b>Debug</b></td><td>
                batch {data.batchID},
                offset {self.repoWidget.state.batchOffsets[data.batchID]+data.offsetInBatch}
                ({self.repoWidget.state.getCommitSequentialIndex(data.hexsha)})
                </td></tr>
            </table>"""

        title = F"Commit info {shortHash(commit.hexsha)}"

        details = commit.message if contd else None

        messageBox = QMessageBox(QMessageBox.Information, title, markup, parent=self)
        messageBox.setDetailedText(details)
        messageBox.exec_()

    def checkoutCurrentCommit(self):
        commitHash = self.currentCommitHash
        if not commitHash:
            return

        def work():
            self.repo.git.checkout(commitHash)

        def onComplete(_):
            self.repoWidget.quickRefresh()

        self.repoWidget._startAsyncWorker(1000, work, onComplete, F"Checking out “{commitHash[:settings.prefs.shortHashChars]}”")

    def cherrypickCurrentCommit(self):
        commitHash = self.currentCommitHash
        if not commitHash:
            return

        def work():
            self.repo.git.cherry_pick(commitHash)

        def onComplete(_):
            self.repoWidget.quickRefresh()

        self.repoWidget._startAsyncWorker(1000, work, onComplete, F"Cherry-picking “{shortHash(commitHash)}”")

    def branchFromCurrentCommit(self):
        hexsha = self.currentCommitHash
        if not hexsha:
            return

        newBranchName, ok = textInputDialog(
            self,
            F"New Branch From {shortHash(hexsha)}",
            F"Enter name for new branch starting from {shortHash(hexsha)}:",
            None)
        if ok:
            self.newBranchFromCommit.emit(newBranchName, hexsha)

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

    def selectUncommittedChanges(self):
        self.setCurrentIndex(self.model().index(0, 0))
