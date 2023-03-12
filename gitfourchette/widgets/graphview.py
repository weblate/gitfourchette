from gitfourchette.actiondef import ActionDef
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.commitlogmodel import CommitLogModel
from gitfourchette.qt import *
from gitfourchette.util import (messageSummary, shortHash, stockIcon, showWarning, asyncMessageBox,
                                askConfirmation, paragraphs)
from gitfourchette.widgets.graphdelegate import GraphDelegate
from gitfourchette.widgets.searchbar import SearchBar
from gitfourchette.widgets.resetheaddialog import ResetHeadDialog
from html import escape
from typing import Literal
import pygit2


class CommitFilter(QSortFilterProxyModel):
    hiddenOids: set[pygit2.Oid]

    def __init__(self, parent):
        super().__init__(parent)
        self.hiddenOids = set()
        self.setDynamicSortFilter(True)

    @property
    def clModel(self) -> CommitLogModel:
        return self.sourceModel()

    def setHiddenCommits(self, hiddenCommits: set[pygit2.Oid]):
        self.hiddenOids = hiddenCommits

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex) -> bool:
        if sourceRow == 0:  # Uncommitted Changes
            return True

        commit = self.clModel._commitSequence[sourceRow - 1]  # -1 to account for Uncommited Changes
        return commit.oid not in self.hiddenOids


class GraphView(QListView):
    uncommittedChangesClicked = Signal()
    emptyClicked = Signal()
    commitClicked = Signal(pygit2.Oid)
    resetHead = Signal(pygit2.Oid, str, bool)
    newBranchFromCommit = Signal(pygit2.Oid)
    checkoutCommit = Signal(pygit2.Oid)
    revertCommit = Signal(pygit2.Oid)
    exportCommitAsPatch = Signal(pygit2.Oid)
    exportWorkdirAsPatch = Signal()
    commitChanges = Signal()
    amendChanges = Signal()
    newStash = Signal()
    widgetMoved = Signal()
    linkActivated = Signal(str)

    clModel: CommitLogModel
    clFilter: CommitFilter

    def __init__(self, parent):
        super().__init__(parent)

        self.clModel = CommitLogModel(self)
        self.clFilter = CommitFilter(self)
        self.clFilter.setSourceModel(self.clModel)

        self.setModel(self.clFilter)

        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # prevents double-clicking to edit row text
        self.setItemDelegate(GraphDelegate(parent, parent=self))

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onContextMenuRequested)

        self.searchBar = SearchBar(self, self.tr("Find Commit"))
        self.searchBar.textChanged.connect(lambda: self.model().layoutChanged.emit())  # Redraw graph view (is this efficient?)
        self.searchBar.searchNext.connect(lambda: self.search("next"))
        self.searchBar.searchPrevious.connect(lambda: self.search("previous"))
        self.widgetMoved.connect(self.searchBar.snapToParent)
        self.searchBar.hide()

    def moveEvent(self, event: QMoveEvent):
        self.widgetMoved.emit()

    def onContextMenuRequested(self, point: QPoint):
        globalPoint = self.mapToGlobal(point)

        oid = self.currentCommitOid

        if not oid:
            actions = [
                ActionDef(self.tr("&Commit Staged Changes..."), self.commitChanges, shortcuts=GlobalShortcuts.commit),
                ActionDef(self.tr("&Amend Last Commit..."), self.amendChanges, shortcuts=GlobalShortcuts.amendCommit),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("&Stash Uncommitted Changes..."), self.newStash, shortcuts=GlobalShortcuts.newStash),
                ActionDef(self.tr("E&xport Uncommitted Changes As Patch..."), self.exportWorkdirAsPatch),
            ]
        else:
            actions = [
                ActionDef(self.tr("&Check Out..."), lambda: self.checkoutCommit.emit(oid)),
                ActionDef(self.tr("Start &Branch from Here..."), lambda: self.newBranchFromCommit.emit(oid), "vcs-branch"),
                ActionDef(self.tr("&Reset HEAD to Here..."), self.resetHeadFlow),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("Cherry &Pick..."), self.cherrypickCurrentCommit),
                ActionDef(self.tr("Re&vert..."), lambda: self.revertCommit.emit(oid)),
                ActionDef(self.tr("E&xport As Patch..."), lambda: self.exportCommitAsPatch.emit(oid)),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("Copy Commit &Hash"), self.copyCommitHashToClipboard),
                ActionDef(self.tr("Get &Info..."), self.getInfoOnCurrentCommit, QStyle.StandardPixmap.SP_MessageBoxInformation),
            ]

        menu = ActionDef.makeQMenu(self, actions)
        menu.setObjectName("GraphViewCM")

        menu.exec(globalPoint)

        menu.deleteLater()

    def clear(self):
        self.setCommitSequence(None)

    def setHiddenCommits(self, hiddenCommits: set[pygit2.Oid]):
        self.clFilter.setHiddenCommits(hiddenCommits)  # update filter BEFORE updating model
        self.clFilter.invalidateFilter()

    def setCommitSequence(self, commitSequence: list[pygit2.Commit] | None):
        self.clModel.setCommitSequence(commitSequence)
        self.onSetCurrent()

    def refreshTopOfCommitSequence(self, nRemovedRows: int, nAddedRows: int, commitSequence: list[pygit2.Commit]):
        self.clModel.refreshTopOfCommitSequence(nRemovedRows, nAddedRows, commitSequence)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        oid = self.currentCommitOid
        if oid:
            self.checkoutCommit.emit(oid)
        else:
            self.commitChanges.emit()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        oid = self.currentCommitOid

        if k in GlobalShortcuts.getCommitInfoHotkeys:
            if oid:
                self.getInfoOnCurrentCommit()
            else:
                QApplication.beep()

        elif k in GlobalShortcuts.checkoutCommitFromGraphHotkeys:
            if oid:
                self.checkoutCommit.emit(self.currentCommitOid)
            else:
                self.commitChanges.emit()

        else:
            super().keyPressEvent(event)

    @property
    def repo(self) -> pygit2.Repository:
        return self.repoWidget.state.repo

    @property
    def currentCommitOid(self) -> pygit2.Oid | None:
        if not self.currentIndex().isValid():
            return
        commit: pygit2.Commit = self.currentIndex().data(CommitLogModel.CommitRole)
        if not commit:  # Uncommitted Changes has no bound data
            return
        return commit.oid

    def getInfoOnCurrentCommit(self):
        oid = self.currentCommitOid
        if not oid:
            return

        debugInfoRequested = QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier

        def formatSignature(sig: pygit2.Signature):
            qdt = QDateTime.fromSecsSinceEpoch(sig.time, Qt.TimeSpec.OffsetFromUTC, sig.offset * 60)
            return F"{escape(sig.name)} &lt;{escape(sig.email)}&gt;<br>" \
                   + "<small>" + escape(QLocale().toString(qdt, QLocale.FormatType.LongFormat)) + "</small>"

        # TODO: we should probably run this as a task

        commit: pygit2.Commit = self.currentIndex().data(CommitLogModel.CommitRole)

        summary, contd = messageSummary(commit.message)

        postSummary = ""
        nLines = len(commit.message.rstrip().split('\n'))

        parentHashes = [F"<a href=\"gitfourchette://commit#{p}\">{shortHash(p)}</a>" for p in commit.parent_ids]
        parentTitle = self.tr("%n parent(s)", "", len(parentHashes))
        parentValueMarkup = ', '.join(parentHashes)

        #childHashes = [shortHash(c) for c in commit.children]
        #childLabelMarkup = escape(fplural('# Child^ren', len(childHashes)))
        #childValueMarkup = escape(', '.join(childHashes))

        authorMarkup = formatSignature(commit.author)

        if commit.author == commit.committer:
            sameAsAuthor = self.tr("(same as author)")
            committerMarkup = F"<i>{sameAsAuthor}</i>"
        else:
            committerMarkup = formatSignature(commit.committer)

        '''
        diffs = porcelain.loadCommitDiffs(self.repo, oid)
        statsMarkup = (
                fplural("<b>#</b> changed file^s", sum(diff.stats.files_changed for diff in diffs)) +
                fplural("<br/><b>#</b> insertion^s", sum(diff.stats.insertions for diff in diffs)) +
                fplural("<br/><b>#</b> deletion^s", sum(diff.stats.deletions for diff in diffs))
        )
        '''

        hashTitle = self.tr("Hash")
        authorTitle = self.tr("Author")
        committerTitle = self.tr("Committer")

        markup = F"""<big>{summary}</big>{postSummary}
            <br>
            <table>
            <tr><td><b>{hashTitle}&nbsp;</b></td><td>{commit.oid.hex}</td></tr>
            <tr><td><b>{parentTitle}&nbsp;</b></td><td>{parentValueMarkup}</td></tr>
            <tr><td><b>{authorTitle}&nbsp;</b></td><td>{authorMarkup}</td></tr>
            <tr><td><b>{committerTitle}&nbsp;</b></td><td>{committerMarkup}</td></tr>
            </table>"""

        if debugInfoRequested:
            state = self.repoWidget.state
            seqIndex = state.getCommitSequentialIndex(oid)
            markup += f"""<hr><b>Top secret debug info</b><br>
                GraphView row: {self.currentIndex().row()}<br>
                Commit sequence index: {seqIndex}<br>
                {state.graph.startPlayback(seqIndex).copyCleanFrame()}
            """

        title = self.tr("Commit info: {0}").format(shortHash(commit.oid))

        details = commit.message if contd else None

        messageBox = asyncMessageBox(self, 'information', title, markup, macShowTitle=False,
                                     buttons=QMessageBox.StandardButton.Ok)

        if details:
            messageBox.setDetailedText(details)

            # Pre-click "Show Details" button
            for button in messageBox.buttons():
                role = messageBox.buttonRole(button)
                if role == QMessageBox.ButtonRole.ActionRole:
                    button.click()
                elif role == QMessageBox.ButtonRole.AcceptRole:
                    messageBox.setDefaultButton(button)

        label: QLabel = messageBox.findChild(QLabel, "qt_msgbox_label")
        assert label
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(lambda: messageBox.close())
        label.linkActivated.connect(self.linkActivated)

        messageBox.show()

    def cherrypickCurrentCommit(self):
        # TODO: This should totally be reworked
        oid = self.currentCommitOid
        if not oid:
            return

        def work():
            self.repo.git.cherry_pick(oid)

        def onComplete(_):
            self.repoWidget.quickRefresh()
            self.selectCommit(oid)

        self.repoWidget._startAsyncWorker(1000, work, onComplete, F"Cherry-picking “{shortHash(oid)}”")

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
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

    def copyCommitHashToClipboard(self):
        oid = self.currentCommitOid
        if not oid:  # uncommitted changes
            return

        QApplication.clipboard().setText(oid.hex)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        # do standard callback, such as scrolling the viewport if reaching the edges, etc.
        super().selectionChanged(selected, deselected)

        if len(selected.indexes()) == 0:
            self.onSetCurrent(None)
        else:
            self.onSetCurrent(selected.indexes()[0])

    def onSetCurrent(self, current: QModelIndex = None):
        if current is None or not current.isValid():
            self.emptyClicked.emit()
        elif current.row() == 0:  # uncommitted changes
            self.uncommittedChangesClicked.emit()
        else:
            oid = current.data(CommitLogModel.CommitRole).oid
            self.commitClicked.emit(oid)

    def selectUncommittedChanges(self):
        self.setCurrentIndex(self.model().index(0, 0))

    def getFilterIndexForCommit(self, oid: pygit2.Oid):
        try:
            rawIndex = self.repoWidget.state.getCommitSequentialIndex(oid)
        except KeyError:
            return None

        newSourceIndex = self.clModel.index(1 + rawIndex, 0)
        newFilterIndex = self.clFilter.mapFromSource(newSourceIndex)
        return newFilterIndex

    def selectCommit(self, oid: pygit2.Oid, silent=False):
        newFilterIndex = self.getFilterIndexForCommit(oid)

        if not newFilterIndex:
            if not silent:
                showWarning(self, self.tr("Commit not found"),
                            self.tr("Commit not found or not loaded:") + f"<br>{oid.hex}")
            return False
        elif newFilterIndex.row() < 0:
            if not silent:
                showWarning(self, self.tr("Hidden commit"),
                            self.tr("This commit is hidden from the log:") + f"<br>{oid.hex}")
            return False

        if self.currentIndex().row() != newFilterIndex.row():
            self.scrollTo(newFilterIndex, QAbstractItemView.ScrollHint.EnsureVisible)
            self.setCurrentIndex(newFilterIndex)
        return True

    def scrollToCommit(self, oid, scrollHint=QAbstractItemView.ScrollHint.EnsureVisible):
        newFilterIndex = self.getFilterIndexForCommit(oid)
        if not newFilterIndex:
            return
        self.scrollTo(newFilterIndex, scrollHint)

    def repaintCommit(self, oid: pygit2.Oid):
        newFilterIndex = self.getFilterIndexForCommit(oid)
        if newFilterIndex:
            self.update(newFilterIndex)

    def refreshPrefs(self):
        self.model().beginResetModel()
        self.model().endResetModel()

    # -------------------------------------------------------------------------
    # Find text in commit message or hash

    def search(self, op: Literal["start", "next", "previous"]):
        self.searchBar.popUp(forceSelectAll=op == "start")

        if op == "start":
            return

        forward = op != "previous"

        if not self.searchBar.sanitizedSearchTerm:
            QApplication.beep()
            return

        if len(self.selectedIndexes()) != 0:
            start = self.currentIndex().row()
        elif forward:
            start = 0
        else:
            start = self.model().rowCount()

        if forward:
            self.searchCommitInRange(range(1 + start, self.model().rowCount()))
        else:
            self.searchCommitInRange(range(start - 1, -1, -1))

    def searchCommitInRange(self, searchRange: range):
        message = self.searchBar.sanitizedSearchTerm
        if not message:
            QApplication.beep()
            return

        likelyHash = False
        if len(message) <= 40:
            try:
                int(message, 16)
                likelyHash = True
            except ValueError:
                pass

        model = self.model()

        for i in searchRange:
            modelIndex = model.index(i, 0)
            meta = model.data(modelIndex, CommitLogModel.CommitRole)
            if meta is None:
                continue
            if (message in meta.message.lower()) or (likelyHash and message in meta.oid.hex):
                self.setCurrentIndex(modelIndex)
                return

        forward = searchRange.step > 0

        def wrapAround():
            if forward:
                newRange = range(0, self.model().rowCount())
            else:
                newRange = range(self.model().rowCount() - 1, 0, -1)
            self.searchCommitInRange(newRange)

        prompt = [
            self.tr("End of commit log reached.") if forward else self.tr("Top of commit log reached."),
            self.tr("No more occurrences of “{0}” found.").format(escape(message))
        ]
        askConfirmation(self, self.tr("Find Commit"), paragraphs(prompt), okButtonText=self.tr("Wrap Around"),
                        messageBoxIcon="information", callback=wrapAround)
