from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.util import messageSummary, fplural, shortHash
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.graphdelegate import GraphDelegate
from gitfourchette.widgets.resetheaddialog import ResetHeadDialog
from html import escape
import pygit2


class GraphView(QListView):
    uncommittedChangesClicked = Signal()
    emptyClicked = Signal()
    commitClicked = Signal(pygit2.Oid)
    resetHead = Signal(str, str, bool)
    newBranchFromCommit = Signal(str, pygit2.Oid)

    def __init__(self, parent):
        super().__init__(parent)
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)  # sinon on peut double-cliquer pour éditer les lignes...
        self.setItemDelegate(GraphDelegate(parent, parent=self))

        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        getInfoAction = QAction("Get Info...", self)
        getInfoAction.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
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
        resetAction = QAction(F"Reset HEAD to Here...", self)
        resetAction.triggered.connect(self.resetHeadFlow)
        self.addAction(resetAction)

    def _replaceModel(self, model):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        self.setModel(model)

    def fill(self, commitSequence: list[pygit2.Commit]):
        model = QStandardItemModel(self)  # creating a model from scratch seems faster than clearing an existing one
        model.appendRow(QStandardItem())
        model.insertRows(1, len(commitSequence))
        for i, meta in enumerate(commitSequence):
            model.setData(model.index(1 + i, 0), meta, Qt.DisplayRole)
        self._replaceModel(model)
        self.onSetCurrent()

    def refreshTop(self, nRemovedRows: int, nAddedRows: int, commitSequence: list[pygit2.Commit]):
        model: QAbstractListModel = self.model()
        model.removeRows(1, nRemovedRows)
        model.insertRows(1, nAddedRows)
        for i in range(nAddedRows):
            model.setData(model.index(1 + i, 0), commitSequence[i], Qt.DisplayRole)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.getInfoOnCurrentCommit()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            self.getInfoOnCurrentCommit()
        else:
            super().keyPressEvent(event)

    @property
    def repo(self) -> pygit2.Repository:
        return self.repoWidget.state.repo

    @property
    def currentCommitOid(self) -> pygit2.Oid:
        if not self.currentIndex().isValid():
            return
        data: pygit2.Commit = self.currentIndex().data()
        if not data:  # Uncommitted Changes has no bound data
            return
        return data.oid

    def getInfoOnCurrentCommit(self):
        oid = self.currentCommitOid
        if not oid:
            return

        def formatSignature(sig: pygit2.Signature):
            qdt = QDateTime.fromSecsSinceEpoch(sig.time, Qt.TimeSpec.OffsetFromUTC, sig.offset * 60)
            return F"{escape(sig.name)} &lt;{escape(commit.author.email)}&gt;<br>" \
                   + escape(QLocale.system().toString(qdt, QLocale.LongFormat))

        # TODO: we should probably run this as a worker; simply adding "with self.repoWidget.state.mutexLocker()" blocks the UI thread ... which also blocks the worker in the background! Is the qthreadpool given "time to breathe" by the GUI thread?

        commit: pygit2.Commit = self.currentIndex().data()

        summary, contd = messageSummary(commit.message)

        postSummary = ""
        nLines = len(commit.message.rstrip().split('\n'))
        if contd:
            postSummary = F"<br>\u25bc <i>click &ldquo;Show Details&rdquo; to reveal full message " \
                  F"({nLines} lines)</i>"

        parentHashes = [shortHash(p) for p in commit.parent_ids]
        parentLabelMarkup = escape(fplural('# Parent^s', len(parentHashes)))
        parentValueMarkup = escape(', '.join(parentHashes))

        #childHashes = [shortHash(c) for c in commit.children]
        #childLabelMarkup = escape(fplural('# Child^ren', len(childHashes)))
        #childValueMarkup = escape(', '.join(childHashes))

        authorMarkup = formatSignature(commit.author)

        if commit.author == commit.committer:
            committerMarkup = F"<i>(same as author)</i>"
        else:
            committerMarkup = formatSignature(commit.committer)

        diffs = porcelain.loadCommitDiffs(self.repo, oid)
        statsMarkup = (
                fplural("<b>#</b> changed file^s", sum(diff.stats.files_changed for diff in diffs)) +
                fplural("<br/><b>#</b> insertion^s", sum(diff.stats.insertions for diff in diffs)) +
                fplural("<br/><b>#</b> deletion^s", sum(diff.stats.deletions for diff in diffs))
        )

        markup = F"""<big>{summary}</big>{postSummary}
            <br>
            <table>
            <tr><td><b>Full Hash </b></td><td>{commit.oid.hex}</td></tr>
            <tr><td><b>{parentLabelMarkup} </b></td><td>{parentValueMarkup}</td></tr>
            <tr><td><b>Author </b></td><td>{authorMarkup}</td></tr>
            <tr><td><b>Committer </b></td><td>{committerMarkup}</td></tr>
            <tr><td><b>Statistics </b></td><td>{statsMarkup}</td></tr>
            </table>"""
            # <tr><td><b>Debug</b></td><td>
            #     batch {data.batchID},
            #     offset {self.repoWidget.state.batchOffsets[data.batchID]+data.offsetInBatch}
            #     ({self.repoWidget.state.getCommitSequentialIndex(data.hexsha)})
            #     </td></tr>

        title = F"pygit2.Commit info {shortHash(commit.oid)}"

        details = commit.message if contd else None

        messageBox = QMessageBox(QMessageBox.Information, title, markup, parent=self)
        messageBox.setDetailedText(details)
        messageBox.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        messageBox.show()

    def checkoutCurrentCommit(self):
        oid = self.currentCommitOid
        if not oid:
            return

        def work():
            self.repo.git.checkout(oid)

        def onComplete(_):
            self.repoWidget.quickRefresh()
            self.repoWidget.sidebar.fill(self.repo)

        self.repoWidget._startAsyncWorker(1000, work, onComplete, F"Checking out “{shortHash(oid)}”")

    def cherrypickCurrentCommit(self):
        oid = self.currentCommitOid
        if not oid:
            return

        def work():
            self.repo.git.cherry_pick(oid)

        def onComplete(_):
            self.repoWidget.quickRefresh()
            self.selectCommit(oid)

        self.repoWidget._startAsyncWorker(1000, work, onComplete, F"Cherry-picking “{shortHash(oid)}”")

    def branchFromCurrentCommit(self):
        oid = self.currentCommitOid
        if not oid:
            return

        def onAccept(newBranchName):
            self.newBranchFromCommit.emit(newBranchName, oid)

        showTextInputDialog(
            self,
            F"New branch from {shortHash(oid)}",
            F"Enter name for new branch starting from {shortHash(oid)}:",
            None,
            onAccept)

    def resetHeadFlow(self):
        oid = self.currentCommitOid
        if not oid:
            return

        dlg = ResetHeadDialog(oid, parent=self)

        def onAccept():
            resetMode = dlg.activeMode
            recurse = dlg.recurseSubmodules
            self.resetHead.emit(oid, resetMode, recurse)

        dlg.accepted.connect(onAccept)
        dlg.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

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
            self.commitClicked.emit(current.data().oid)

    def selectUncommittedChanges(self):
        self.setCurrentIndex(self.model().index(0, 0))

    def selectCommit(self, oid: pygit2.Oid):
        try:
            index = self.repoWidget.state.getCommitSequentialIndex(oid)
        except KeyError:
            QMessageBox.warning(self, "pygit2.Commit not found",
                                F"pygit2.Commit not found or not loaded:\n{oid.hex}")
            return False
        ci = self.currentIndex()
        newRow = 1 + index
        if ci.row() != newRow:
            self.setCurrentIndex(self.model().index(1 + index, 0))
            return True
        else:
            return False
