from typing import Literal

from contextlib import suppress

from gitfourchette import settings
from gitfourchette.forms.resetheaddialog import ResetHeadDialog
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.graphview.commitlogdelegate import CommitLogDelegate
from gitfourchette.graphview.commitlogfilter import CommitLogFilter
from gitfourchette.graphview.commitlogmodel import CommitLogModel
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks import *
from gitfourchette.toolbox import *


class GraphView(QListView):
    jump = Signal(NavLocator)
    widgetMoved = Signal()
    linkActivated = Signal(str)
    statusMessage = Signal(str)

    clModel: CommitLogModel
    clFilter: CommitLogFilter

    class SelectCommitError(KeyError):
        def __init__(self, oid: Oid, foundButHidden: bool):
            super().__init__()
            self.oid = oid
            self.foundButHidden = foundButHidden

        def __str__(self):
            if self.foundButHidden:
                m = translate("GraphView", "Commit “{0}” isn’t shown in the graph because it is part of a hidden branch.")
            else:
                m = translate("GraphView", "Commit “{0}” isn’t shown in the graph.")
            return m.format(shortHash(self.oid))

    def __init__(self, parent):
        super().__init__(parent)

        self.clModel = CommitLogModel(self)
        self.clFilter = CommitLogFilter(self)
        self.clFilter.setSourceModel(self.clModel)

        self.setModel(self.clFilter)

        # Massive perf boost when displaying/updating huge commit logs
        self.setUniformItemSizes(True)

        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # prevents double-clicking to edit row text
        self.setItemDelegate(CommitLogDelegate(parent, parent=self))

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onContextMenuRequested)

        self.searchBar = SearchBar(self, self.tr("Find Commit"))
        self.searchBar.textChanged.connect(lambda: self.model().layoutChanged.emit())  # Redraw graph view (is this efficient?)
        self.searchBar.searchNext.connect(lambda: self.search("next"))
        self.searchBar.searchPrevious.connect(lambda: self.search("previous"))
        self.searchBar.searchPulse.connect(self.searchPulse)
        self.widgetMoved.connect(self.searchBar.snapToParent)
        self.searchBar.hide()

    def moveEvent(self, event: QMoveEvent):
        self.widgetMoved.emit()

    def makeContextMenu(self):
        oid = self.currentCommitOid

        if not oid:
            actions = [
                TaskBook.action(NewCommit, "&C"),
                TaskBook.action(AmendCommit, "&A"),
                ActionDef.SEPARATOR,
                TaskBook.action(NewStash, "&S"),
                TaskBook.action(ExportWorkdirAsPatch, "&X"),
            ]
        else:
            actions = [
                TaskBook.action(NewBranchFromCommit, self.tr("Start &Branch from Here..."), taskArgs=oid),
                TaskBook.action(NewTag, self.tr("&Tag This Commit..."), taskArgs=oid),
                ActionDef.SEPARATOR,
                TaskBook.action(CheckoutCommit, self.tr("&Check Out..."), taskArgs=oid),
                ActionDef(self.tr("&Reset HEAD to Here..."), self.resetHeadFlow),
                ActionDef.SEPARATOR,
                TaskBook.action(CherrypickCommit, self.tr("Cherry &Pick..."), taskArgs=oid),
                TaskBook.action(RevertCommit, self.tr("Re&vert..."), taskArgs=oid),
                TaskBook.action(ExportCommitAsPatch, self.tr("E&xport As Patch..."), taskArgs=oid),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("Copy Commit &Hash"), self.copyCommitHashToClipboard),
                ActionDef(self.tr("Get &Info..."), self.getInfoOnCurrentCommit, QStyle.StandardPixmap.SP_MessageBoxInformation),
            ]

        menu = ActionDef.makeQMenu(self, actions)
        menu.setObjectName("GraphViewCM")

        return menu

    def onContextMenuRequested(self, point: QPoint):
        globalPoint = self.mapToGlobal(point)
        menu = self.makeContextMenu()
        menu.exec(globalPoint)
        menu.deleteLater()

    def clear(self):
        self.setCommitSequence(None)

    @benchmark
    def setHiddenCommits(self, hiddenCommits: set[Oid]):
        # Invalidating the filter can be costly, so avoid if possible
        if self.clFilter.hiddenOids == hiddenCommits:
            return

        self.clFilter.setHiddenCommits(hiddenCommits)  # update filter BEFORE updating model
        self.clFilter.invalidateFilter()

    @benchmark
    def setCommitSequence(self, commitSequence: list[Commit] | None):
        self.clModel.setCommitSequence(commitSequence)
        self.onSetCurrent()

    @benchmark
    def refreshTopOfCommitSequence(self, nRemovedRows: int, nAddedRows: int, commitSequence: list[Commit]):
        self.clModel.refreshTopOfCommitSequence(nRemovedRows, nAddedRows, commitSequence)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            oid = self.currentCommitOid
            if oid:
                CheckoutCommit.invoke(oid)
            else:
                NewCommit.invoke()
        else:
            super().mouseDoubleClickEvent(event)

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
                CheckoutCommit.invoke(oid)
            else:
                NewCommit.invoke()

        else:
            super().keyPressEvent(event)

    @property
    def repo(self) -> Repo:
        return self.repoWidget.state.repo

    @property
    def currentCommitOid(self) -> Oid | None:
        if not self.currentIndex().isValid():
            return
        oid = self.currentIndex().data(CommitLogModel.OidRole)
        return oid

    def getInfoOnCurrentCommit(self):
        oid = self.currentCommitOid
        if not oid:
            return

        debugInfoRequested = QGuiApplication.keyboardModifiers() & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)

        def formatSignature(sig: Signature):
            qdt = QDateTime.fromSecsSinceEpoch(sig.time, Qt.TimeSpec.OffsetFromUTC, sig.offset * 60)
            return F"{escape(sig.name)} &lt;{escape(sig.email)}&gt;<br>" \
                   + "<small>" + escape(QLocale().toString(qdt, QLocale.FormatType.LongFormat)) + "</small>"

        # TODO: we should probably run this as a task

        commit: Commit = self.currentIndex().data(CommitLogModel.CommitRole)

        summary, contd = messageSummary(commit.message)
        details = commit.message if contd else ""

        postSummary = ""

        parentHashes = []
        for p in commit.parent_ids:
            parentHashes.append(NavLocator.inCommit(p).toHtml("[" + shortHash(p) + "]"))

        parentTitle = self.tr("%n parent(s)", "", len(parentHashes))
        parentValueMarkup = ', '.join(parentHashes)

        likelyShallowRoot = len(parentHashes) == 0 and self.repo.is_shallow
        if likelyShallowRoot:
            parentTitle += "*"

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
        diffs = self.repo.commit_diffs(oid)
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
            """

        if debugInfoRequested:
            state = self.repoWidget.state
            seqIndex = state.graph.getCommitRow(oid)
            frame = state.graph.getFrame(seqIndex)
            homeChainTopRow = frame.getHomeChainForCommit().topRow
            homeChainTopOid = state.graph.getFrame(homeChainTopRow).commit
            homeChainLocator = NavLocator.inCommit(homeChainTopOid)
            markup += F"""
                <tr><td><b>View row</b></td><td>{self.currentIndex().row()}</td></tr>
                <tr><td><b>Graph row</b></td><td>{repr(state.graph.commitRows[oid])}</td></tr>
                <tr><td><b>Home chain</b></td><td>{repr(homeChainTopRow)} ({homeChainLocator.toHtml(shortHash(homeChainTopOid))})</td></tr>
                <tr><td><b>Arcs</b></td><td>{len(frame.openArcs)} open, {len(frame.solvedArcs)} solved</td></tr>
            """
            details = str(frame) + "\n\n" + details

        markup += "</table>"

        if likelyShallowRoot:
            markup += "<p>* <em>" + self.tr(
                "You’re working in a shallow clone of the repository; the full commit log isn’t available. "
                "This commit may actually have parents in the full history."
            ) + "</em></p>"

        title = self.tr("Commit info: {0}").format(shortHash(commit.oid))

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

    def resetHeadFlow(self):
        oid = self.currentCommitOid
        if not oid:
            return

        dlg = ResetHeadDialog(oid, parent=self)

        def onAccept():
            resetMode = dlg.activeMode
            recurse = dlg.recurseSubmodules
            ResetHead.invoke(oid, resetMode, recurse)

        dlg.accepted.connect(onAccept)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

    def copyCommitHashToClipboard(self):
        oid = self.currentCommitOid
        if not oid:  # uncommitted changes
            return

        text = oid.hex
        QApplication.clipboard().setText(text)
        self.statusMessage.emit(clipboardStatusMessage(text))

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        # do standard callback, such as scrolling the viewport if reaching the edges, etc.
        super().selectionChanged(selected, deselected)

        if selected.count() == 0:
            self.onSetCurrent(None)
        else:
            self.onSetCurrent(selected.indexes()[0])

    def onSetCurrent(self, current: QModelIndex = None):
        if current is None or not current.isValid():
            locator = NavLocator(NavContext.EMPTY)
        else:
            oid = current.data(CommitLogModel.OidRole)
            if oid:
                locator = NavLocator(NavContext.COMMITTED, commit=oid)
            else:  # uncommitted changes
                locator = NavLocator(NavContext.WORKDIR)
        self.jump.emit(locator)

    def selectUncommittedChanges(self, force=False):
        if force or self.currentCommitOid is not None:
            # TODO: Actual lookup
            self.setCurrentIndex(self.model().index(0, 0))

    def getFilterIndexForCommit(self, oid: Oid) -> QModelIndex | None:
        try:
            rawIndex = self.repoWidget.state.graph.getCommitRow(oid)
        except KeyError:
            raise GraphView.SelectCommitError(oid, foundButHidden=False)

        newSourceIndex = self.clModel.index(rawIndex, 0)
        newFilterIndex = self.clFilter.mapFromSource(newSourceIndex)

        if not newFilterIndex.isValid():
            raise GraphView.SelectCommitError(oid, foundButHidden=True)

        return newFilterIndex

    def getFilterIndexError(self, filterIndex: QModelIndex, oid: Oid) -> str:
        if filterIndex is None:
            return self.tr("Commit “{0}” not found or not loaded.").format(shortHash(oid))
        elif not filterIndex.isValid():
            return self.tr("Cannot jump to commit “{0}” because it is on a hidden branch.").format(shortHash(oid))
        else:
            return ""

    def selectCommit(self, oid: Oid, silent=True):
        with suppress(GraphView.SelectCommitError if silent else ()):
            filterIndex = self.getFilterIndexForCommit(oid)
            if filterIndex.row() != self.currentIndex().row():
                self.scrollTo(filterIndex, QAbstractItemView.ScrollHint.EnsureVisible)
                self.setCurrentIndex(filterIndex)

    def scrollToCommit(self, oid: Oid, scrollHint=QAbstractItemView.ScrollHint.EnsureVisible):
        with suppress(GraphView.SelectCommitError):
            filterIndex = self.getFilterIndexForCommit(oid)
            self.scrollTo(filterIndex, scrollHint)

    def repaintCommit(self, oid: Oid):
        with suppress(GraphView.SelectCommitError):
            filterIndex = self.getFilterIndexForCommit(oid)
            self.update(filterIndex)

    def refreshPrefs(self):
        # Force redraw to reflect changes in row height, flattening, date format, etc.
        self.itemDelegate().invalidateMetrics()
        self.model().layoutChanged.emit()

    # -------------------------------------------------------------------------
    # Find text in commit message or hash

    def search(self, op: Literal["start", "next", "previous"], didWrap=False):
        self.searchBar.popUp(forceSelectAll=op == "start")

        if op == "start":
            return

        if not self.searchBar.searchTerm:  # user probably hit F3 without having searched before
            return

        forward = op != "previous"

        if not didWrap and len(self.selectedIndexes()) != 0:
            start = self.currentIndex().row()
        elif forward:
            start = 0
        else:
            start = self.model().rowCount()

        if forward:
            searchRange = range(1 + start, self.model().rowCount())
        else:
            searchRange = range(start - 1, -1, -1)

        # Perform search within range
        index = self.searchCommitInRange(searchRange)

        # A valid index was found in the range, select it
        if index:
            # TODO: What happens if the index is filtered out?
            self.setCurrentIndex(index)
            return

        # No valid index from this point on
        if not didWrap:
            # Wrap around once
            self.search(op, didWrap=True)
        else:
            displayTerm = escape(self.searchBar.rawSearchTerm)
            showInformation(self, self.tr("Find Commit"), self.tr("“{0}” not found.").format(displayTerm))

    def getVisibleRowRange(self) -> range:
        model = self.model()  # to filter out hidden rows, don't use self.clModel directly

        rect = self.viewport().contentsRect()
        top = self.indexAt(rect.topLeft())
        if not top.isValid():
            return range(-1)

        bottom = self.indexAt(rect.bottomLeft())
        if not bottom.isValid():
            bottom = model.index(model.rowCount() - 1, 0)

        return range(top.row(), bottom.row()+1)

    def searchPulse(self):
        # First see if in visible range
        visibleRange = self.getVisibleRowRange()
        index = self.searchCommitInRange(visibleRange)
        if index:
            self.setCurrentIndex(index)
            return

        # It's not visible, so search below visible range first
        searchRange = range(visibleRange.stop, self.model().rowCount())
        index = self.searchCommitInRange(searchRange)
        if index:
            self.setCurrentIndex(index)
            return

        # Finally, search above the visible range
        searchRange = range(0, visibleRange.start)
        index = self.searchCommitInRange(searchRange)
        if index:
            self.setCurrentIndex(index)
            return

        self.searchBar.turnRed()

    def searchCommitInRange(self, searchRange: range) -> QModelIndex | None:
        model = self.model()  # to filter out hidden rows, don't use self.clModel directly

        term = self.searchBar.searchTerm
        likelyHash = self.searchBar.searchTermLooksLikeHash
        assert term
        assert term == term.lower(), "search term should have been sanitized"

        for i in searchRange:
            index = model.index(i, 0)
            commit = model.data(index, CommitLogModel.CommitRole)
            if commit is None:
                continue
            if likelyHash and commit.hex.startswith(term):
                return index
            if term in commit.message.lower():
                return index
            if term in abbreviatePerson(commit.author, settings.prefs.authorDisplayStyle).lower():
                return index

        return None
