from typing import Literal

from contextlib import suppress

from gitfourchette import settings
from gitfourchette.forms.resetheaddialog import ResetHeadDialog
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.graphview.commitlogdelegate import CommitLogDelegate
from gitfourchette.graphview.commitlogfilter import CommitLogFilter
from gitfourchette.graphview.commitlogmodel import CommitLogModel, SpecialRow
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks import *
from gitfourchette.toolbox import *


class GraphView(QListView):
    linkActivated = Signal(str)
    statusMessage = Signal(str)

    clModel: CommitLogModel
    clFilter: CommitLogFilter

    class SelectCommitError(KeyError):
        def __init__(self, oid: Oid, foundButHidden: bool, likelyTruncated: bool = False):
            super().__init__()
            self.oid = oid
            self.foundButHidden = foundButHidden
            self.likelyTruncated = likelyTruncated

        def __str__(self):
            if self.foundButHidden:
                m = translate("GraphView", "Commit {0} isn’t shown in the graph because it is part of a hidden branch.")
            elif self.likelyTruncated:
                m = translate("GraphView", "Commit {0} isn’t shown in the graph because it isn’t part of the truncated commit history.")
            else:
                m = translate("GraphView", "Commit {0} isn’t shown in the graph.")
            return m.format(tquo(shortHash(self.oid)))

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

        self.searchBar = SearchBar(self, self.tr("Find a commit by hash, message or authorFind commit"))
        self.searchBar.detectHashes = True
        self.searchBar.setUpItemViewBuddy()
        self.searchBar.hide()

        self.refreshPrefs(invalidateMetrics=False)

    def makeContextMenu(self):
        kind = self.currentRowKind
        oid = self.currentCommitId
        state = self.repoWidget.state

        mergeActions = []

        if kind == SpecialRow.UncommittedChanges:
            actions = [
                TaskBook.action(self, NewCommit, "&C"),
                TaskBook.action(self, AmendCommit, "&A"),
                ActionDef.SEPARATOR,
                TaskBook.action(self, NewStash, "&S"),
                TaskBook.action(self, ExportWorkdirAsPatch, "&X"),
            ]

        elif kind == SpecialRow.EndOfShallowHistory:
            return None

        elif kind == SpecialRow.TruncatedHistory:
            expandSome = makeInternalLink("expandlog")
            expandAll = makeInternalLink("expandlog", n=str(0))
            changePref = makeInternalLink("prefs", "maxCommits")
            actions = [
                ActionDef(self.tr("Load up to {0} commits").format(QLocale().toString(state.nextTruncationThreshold)),
                          lambda: self.linkActivated.emit(expandSome)),
                ActionDef(self.tr("Load full commit history"),
                          lambda: self.linkActivated.emit(expandAll)),
                ActionDef(self.tr("Change threshold setting"),
                          lambda: self.linkActivated.emit(changePref)),
            ]

        elif kind == SpecialRow.Commit:
            # Merge actions
            if state.homeBranch:
                with suppress(KeyError, StopIteration):
                    rrc = state.reverseRefCache[oid]
                    target = next(ref for ref in rrc if ref.startswith((RefPrefix.HEADS, RefPrefix.REMOTES)))
                    mergeCaption = self.tr("&Merge into {0}...").format(lquo(state.homeBranch))
                    mergeActions = [
                        TaskBook.action(self, MergeBranch, name=mergeCaption, taskArgs=(target,)),
                    ]

            checkoutAction = TaskBook.action(self, CheckoutCommit, self.tr("&Check Out..."), taskArgs=oid)
            checkoutAction.setShortcut(QKeySequence("Return"))

            actions = [
                *mergeActions,
                ActionDef.SEPARATOR,
                TaskBook.action(self, NewBranchFromCommit, self.tr("Start &Branch from Here..."), taskArgs=oid),
                TaskBook.action(self, NewTag, self.tr("&Tag This Commit..."), taskArgs=oid),
                ActionDef.SEPARATOR,
                checkoutAction,
                TaskBook.action(self, ResetHead, self.tr("&Reset HEAD to Here..."), taskArgs=oid),
                ActionDef.SEPARATOR,
                TaskBook.action(self, CherrypickCommit, self.tr("Cherry &Pick..."), taskArgs=oid),
                TaskBook.action(self, RevertCommit, self.tr("Re&vert..."), taskArgs=oid),
                TaskBook.action(self, ExportCommitAsPatch, self.tr("E&xport As Patch..."), taskArgs=oid),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("Copy Commit &Hash"), self.copyCommitHashToClipboard, shortcuts=GlobalShortcuts.copy),
                ActionDef(self.tr("Get &Info..."), self.getInfoOnCurrentCommit, "SP_MessageBoxInformation", shortcuts=QKeySequence("Space")),
            ]

        menu = ActionDef.makeQMenu(self, actions)
        menu.setObjectName("GraphViewCM")

        return menu

    def onContextMenuRequested(self, point: QPoint):
        menu = self.makeContextMenu()
        if menu is not None:
            globalPoint = self.mapToGlobal(point)
            menu.exec(globalPoint)
            menu.deleteLater()

    def clear(self):
        self.setCommitSequence(None)

    @benchmark
    def setHiddenCommits(self, hiddenCommits: set[Oid]):
        # Invalidating the filter can be costly, so avoid if possible
        if self.clFilter.hiddenIds == hiddenCommits:
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
        currentIndex = self.currentIndex()
        if not currentIndex.isValid() or event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        event.accept()
        rowKind = currentIndex.data(CommitLogModel.SpecialRowRole)
        if rowKind == SpecialRow.UncommittedChanges:
            NewCommit.invoke(self)
        elif rowKind == SpecialRow.TruncatedHistory:
            self.linkActivated.emit(makeInternalLink("expandlog"))
        elif rowKind == SpecialRow.Commit:
            oid = self.currentCommitId
            CheckoutCommit.invoke(self, oid)

    def keyPressEvent(self, event: QKeyEvent):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copyCommitHashToClipboard()
            return

        k = event.key()
        oid = self.currentCommitId

        if k in GlobalShortcuts.getCommitInfoHotkeys:
            if oid:
                self.getInfoOnCurrentCommit()
            else:
                QApplication.beep()

        elif k in GlobalShortcuts.checkoutCommitFromGraphHotkeys:
            if oid:
                CheckoutCommit.invoke(self, oid)
            else:
                NewCommit.invoke(self)

        elif k == Qt.Key.Key_Escape:
            if self.searchBar.isVisible():  # close search bar if it doesn't have focus
                self.searchBar.hide()
            else:
                QApplication.beep()

        else:
            super().keyPressEvent(event)

    @property
    def repo(self) -> Repo:
        return self.repoWidget.state.repo

    @property
    def currentRowKind(self) -> SpecialRow:
        currentIndex = self.currentIndex()
        if not currentIndex.isValid():
            return SpecialRow.Invalid
        return currentIndex.data(CommitLogModel.SpecialRowRole)

    @property
    def currentCommitId(self) -> Oid | None:
        if not self.currentIndex().isValid():
            return
        oid = self.currentIndex().data(CommitLogModel.OidRole)
        return oid

    def getInfoOnCurrentCommit(self):
        oid = self.currentCommitId
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

        parentTitle = self.tr("%n Parents:", "singular form can just say 'Parent'", len(parentHashes))
        parentValueMarkup = ', '.join(parentHashes)

        if len(parentHashes) == 0:
            parentTitle = self.tr("No Parent")

            if self.repo.is_shallow:
                parentTitle = self.tr("No Parent?")
                parentValueMarkup += "<p><em>" + self.tr(
                    "You’re working in a shallow clone. This commit may actually have parents in the full history."
                ) + "</em></p>"

        authorMarkup = formatSignature(commit.author)

        if commit.author == commit.committer:
            sameAsAuthor = self.tr("(same as author)")
            committerMarkup = F"<i>{sameAsAuthor}</i>"
        else:
            committerMarkup = formatSignature(commit.committer)

        hashTitle = self.tr("Hash:")
        authorTitle = self.tr("Author:")
        committerTitle = self.tr("Committer:")

        stylesheet = f"""\
        table {{ margin-top: 16px; }}
        th {{ text-align: right; padding-right: 8px; font-weight: normal; color: {mutedTextColorHex(self)}; white-space: pre; }}
        th, td {{ padding-bottom: 4px; }}
        """

        markup = F"""<style>{stylesheet}</style>
            <big>{summary}</big>{postSummary}
            <table>
            <tr><th>{hashTitle}</th><td>{commit.id}</td></tr>
            <tr><th>{parentTitle}</th><td>{parentValueMarkup}</td></tr>
            <tr><th>{authorTitle}</th><td>{authorMarkup}</td></tr>
            <tr><th>{committerTitle}</th><td>{committerMarkup}</td></tr>
            """

        if debugInfoRequested:
            state = self.repoWidget.state
            seqIndex = state.graph.getCommitRow(oid)
            frame = state.graph.getFrame(seqIndex)
            homeChain = frame.getHomeChainForCommit()
            homeChainTopRow = homeChain.topRow
            homeChainTopId = state.graph.getFrame(homeChainTopRow).commit
            if type(homeChainTopId) is Oid:
                homeChainLocator = NavLocator.inCommit(homeChainTopId)
                homeChainTopLink = homeChainLocator.toHtml(shortHash(homeChainTopId))
            else:
                homeChainTopLink = str(homeChainTopId)
            markup += F"""
                <tr><th>View row:</th><td>{self.currentIndex().row()}</td></tr>
                <tr><th>Graph row:</th><td>{repr(state.graph.commitRows[oid])}</td></tr>
                <tr><th>Home chain:</th><td>{repr(homeChainTopRow)} {homeChainTopLink} ({id(homeChain) & 0xFFFFFFFF:X})</td></tr>
                <tr><th>Arcs:</th><td>{len(frame.openArcs)} open, {len(frame.solvedArcs)} solved</td></tr>
            """
            details = str(frame) + "\n\n" + details

        markup += "</table>"

        title = self.tr("Commit info: {0}").format(shortHash(commit.id))

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

    def copyCommitHashToClipboard(self):
        oid = self.currentCommitId
        if not oid:  # uncommitted changes
            return

        text = str(oid)
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
        if self.signalsBlocked():  # Don't bother with the jump if our signals are blocked
            return

        if current is None or not current.isValid():
            locator = NavLocator(NavContext.EMPTY)
        else:
            special = current.data(CommitLogModel.SpecialRowRole)
            if special == SpecialRow.UncommittedChanges:
                locator = NavLocator(NavContext.WORKDIR)
            elif special == SpecialRow.Commit:
                oid = current.data(CommitLogModel.OidRole)
                locator = NavLocator(NavContext.COMMITTED, commit=oid)
            else:
                locator = NavLocator(NavContext.SPECIAL, path=str(special))
        Jump.invoke(self, locator)

    def selectRowForLocator(self, locator: NavLocator, force=False):
        filterIndex = self.getFilterIndexForLocator(locator)
        if force or filterIndex.row() != self.currentIndex().row():
            self.scrollTo(filterIndex, QAbstractItemView.ScrollHint.EnsureVisible)
            self.setCurrentIndex(filterIndex)
        return filterIndex

    def getFilterIndexForLocator(self, locator: NavLocator):
        if locator.context == NavContext.COMMITTED:
            index = self.getFilterIndexForCommit(locator.commit)
            assert index.data(CommitLogModel.SpecialRowRole) == SpecialRow.Commit
        elif locator.context.isWorkdir():
            index = self.clFilter.index(0, 0)
            assert index.data(CommitLogModel.SpecialRowRole) == SpecialRow.UncommittedChanges
        elif locator.context == NavContext.SPECIAL:
            if self.clModel._extraRow == SpecialRow.Invalid:
                raise ValueError("no special row")
            index = self.clFilter.index(self.clFilter.rowCount()-1, 0)
            assert locator.path == str(index.data(CommitLogModel.SpecialRowRole))
        else:
            raise NotImplementedError(f"unsupported locator context {locator.context}")
        return index

    def getFilterIndexForCommit(self, oid: Oid) -> QModelIndex | None:
        try:
            rawIndex = self.repoWidget.state.graph.getCommitRow(oid)
        except KeyError:
            raise GraphView.SelectCommitError(oid, foundButHidden=False, likelyTruncated=self.repoWidget.state.truncatedHistory)

        newSourceIndex = self.clModel.index(rawIndex, 0)
        newFilterIndex = self.clFilter.mapFromSource(newSourceIndex)

        if not newFilterIndex.isValid():
            raise GraphView.SelectCommitError(oid, foundButHidden=True)

        return newFilterIndex

    def scrollToRowForLocator(self, locator: NavLocator, scrollHint=QAbstractItemView.ScrollHint.EnsureVisible):
        with suppress(GraphView.SelectCommitError):
            filterIndex = self.getFilterIndexForLocator(locator)
            self.scrollTo(filterIndex, scrollHint)

    def repaintCommit(self, oid: Oid):
        with suppress(GraphView.SelectCommitError):
            filterIndex = self.getFilterIndexForCommit(oid)
            self.update(filterIndex)

    def refreshPrefs(self, invalidateMetrics=True):
        self.setVerticalScrollMode(settings.prefs.listViewScrollMode)
        self.setAlternatingRowColors(settings.prefs.alternatingRowColors)

        # Force redraw to reflect changes in row height, flattening, date format, etc.
        if invalidateMetrics:
            self.itemDelegate().invalidateMetrics()
            self.model().layoutChanged.emit()

    # -------------------------------------------------------------------------
    # Find text in commit message or hash

    def searchRange(self, searchRange: range) -> QModelIndex | None:
        # print(searchRange)
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
            if likelyHash and str(commit.id).startswith(term):
                return index
            if term in commit.message.lower():
                return index
            if term in abbreviatePerson(commit.author, settings.prefs.authorDisplayStyle).lower():
                return index

        return None
