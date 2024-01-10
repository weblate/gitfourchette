import contextlib

from gitfourchette.tasks import *
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.sidebar.sidebardelegate import SidebarDelegate
from gitfourchette.sidebar.sidebarmodel import (SidebarModel, EItem, UNINDENT_ITEMS, LEAF_ITEMS, ALWAYS_EXPAND,
                                                ROLE_EITEM, ROLE_ISHIDDEN, ROLE_REF, ROLE_USERDATA)
from gitfourchette.toolbox import *


class Sidebar(QTreeView):
    uncommittedChangesClicked = Signal()
    refClicked = Signal(str)
    commitClicked = Signal(Oid)
    toggleHideStash = Signal(Oid)
    toggleHideBranch = Signal(str)

    rebaseActiveOntoBranch = Signal(str)
    pushBranch = Signal(str)

    openSubmoduleRepo = Signal(str)
    openSubmoduleFolder = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("sidebar")  # for styling
        self.setMinimumWidth(128)
        self.setIndentation(16)
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.setItemDelegate(SidebarDelegate(self))

        self.setModel(SidebarModel(self))

        self.setAnimated(True)
        self.setUniformRowHeights(True)  # large sidebars update twice as fast with this, but we can't have thin spacers

        self.expanded.connect(self.onExpanded)
        self.collapsed.connect(self.onCollapsed)
        self.collapseCacheValid = False
        self.collapseCache = set()

        self.expandTriangleClickIndex = None
        self.eatDoubleClickTimer = QElapsedTimer()

    def switchMode(self, modeId: int):
        model: SidebarModel = self.model()
        model.switchMode(modeId)
        self.restoreExpandedItems()

    def visualRect(self, index: QModelIndex) -> QRect:
        """Required so the theme can properly draw unindented rows.
        The offset should match that in SidebarDelegate."""

        vr = super().visualRect(index)

        if index.isValid():
            with contextlib.suppress(ValueError):
                item = SidebarModel.unpackItem(index)

                if item in UNINDENT_ITEMS:
                    unindentLevels = UNINDENT_ITEMS[item]
                    unindentPixels = unindentLevels * self.indentation()
                    vr.adjust(unindentPixels, 0, 0, 0)

        return vr

    def updateHiddenBranches(self, hiddenBranches: list[str]):
        self.model().updateHiddenBranches(hiddenBranches)

    def generateMenuForEntry(self, item: EItem, data: str = "", menu: QMenu = None, index: QModelIndex = None):
        if menu is None:
            menu = QMenu(self)
            menu.setObjectName("SidebarContextMenu")

        actions = []

        if item == EItem.UncommittedChanges:
            actions += [
                TaskBook.action(NewCommit, "&C"),
                TaskBook.action(AmendCommit, "&A"),
                ActionDef.SEPARATOR,
                TaskBook.action(NewStash, "&S"),
                TaskBook.action(ExportWorkdirAsPatch, "&X"),
            ]

        elif item == EItem.LocalBranchesHeader:
            actions += [
                TaskBook.action(NewBranchFromHead, self.tr("&New Branch...")),
            ]

        elif item == EItem.LocalBranch:
            model: SidebarModel = self.model()
            repo = model.repo
            branch = repo.branches.local[data]

            activeBranchName = repo.head_branch_shorthand
            isCurrentBranch = branch and branch.is_checked_out()
            hasUpstream = bool(branch.upstream)
            upstreamBranchName = ""
            if branch.upstream:
                upstreamBranchName = branch.upstream.shorthand

            isBranchHidden = False
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)

            thisBranchDisplay = elide(data)
            activeBranchDisplay = elide(activeBranchName)
            upstreamBranchDisplay = elide(upstreamBranchName)

            actions += [
                TaskBook.action(
                    SwitchBranch,
                    self.tr("&Switch to “{0}”").format(thisBranchDisplay),
                    taskArgs=(data, False),  # False: don't ask for confirmation
                    enabled=not isCurrentBranch,
                ),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Merge “{0}” into “{1}”...").format(thisBranchDisplay, activeBranchDisplay),
                          lambda: MergeBranch.invoke(data),
                          icon="vcs-merge",
                          enabled=not isCurrentBranch and activeBranchName),

                ActionDef(self.tr("&Rebase “{0}” onto “{1}”...").format(activeBranchDisplay, thisBranchDisplay),
                          lambda: self.rebaseActiveOntoBranch.emit(data),
                          enabled=not isCurrentBranch and activeBranchName),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Push..."),
                          lambda: self.pushBranch.emit(data),
                          "vcs-push",
                          shortcuts=GlobalShortcuts.pushBranch,
                          statusTip=self.tr("Upload your commits to the remote server")),

                TaskBook.action(
                    FetchRemoteBranch,
                    self.tr("&Fetch..."),
                    taskArgs=branch.upstream.shorthand if hasUpstream else None,
                    enabled=hasUpstream,
                ),

                TaskBook.action(
                    FastForwardBranch,
                    self.tr("Fast-Forward to “{0}”...").format(upstreamBranchDisplay) if upstreamBranchName else self.tr("Fast-Forward..."),
                    taskArgs=data,
                    enabled=hasUpstream,
                ),

                TaskBook.action(EditTrackedBranch, self.tr("Set &Tracked Branch..."), taskArgs=data),

                ActionDef.SEPARATOR,

                TaskBook.action(RenameBranch, self.tr("Re&name..."), taskArgs=data),

                TaskBook.action(DeleteBranch, self.tr("&Delete..."), taskArgs=data),

                ActionDef.SEPARATOR,

                TaskBook.action(NewBranchFromLocalBranch, self.tr("New &Branch from Here..."), taskArgs=data),

                ActionDef.SEPARATOR,

                ActionDef(
                    self.tr("&Hide in Graph"),
                    lambda: self.toggleHideBranch.emit("refs/heads/" + data),
                    checkState=1 if isBranchHidden else -1,
                    statusTip=self.tr("Hide this branch from the graph (effective if no other branches/tags point here)"),
                ),
            ]

        elif item == EItem.DetachedHead:
            actions += [TaskBook.action(NewBranchFromHead, self.tr("New &Branch from Here...")), ]

        elif item == EItem.RemoteBranch:
            isBranchHidden = False
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)

            actions += [
                TaskBook.action(
                    NewTrackingBranch,
                    self.tr("New local branch tracking “{0}”...").format(escamp(elide(data))),
                    taskArgs=data
                ),

                TaskBook.action(FetchRemoteBranch, self.tr("Fetch this remote branch..."), taskArgs=data),

                ActionDef.SEPARATOR,

                TaskBook.action(RenameRemoteBranch, self.tr("Rename branch on remote..."), taskArgs=data),

                TaskBook.action(DeleteRemoteBranch, self.tr("Delete branch on remote..."), taskArgs=data),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide in Graph"),
                          lambda: self.toggleHideBranch.emit("refs/remotes/" + data),
                          checkState=1 if isBranchHidden else -1),
            ]

        elif item == EItem.Remote:
            actions += [
                TaskBook.action(EditRemote, self.tr("&Edit Remote..."), taskArgs=data),

                TaskBook.action(FetchRemote, self.tr("&Fetch All Remote Branches..."), taskArgs=data),

                ActionDef.SEPARATOR,

                TaskBook.action(DeleteRemote, self.tr("&Remove Remote..."), taskArgs=data),
            ]

        elif item == EItem.RemotesHeader:
            actions += [
                TaskBook.action(NewRemote, "&A"),
            ]

        elif item == EItem.StashesHeader:
            actions += [
                TaskBook.action(NewStash, "&S"),
            ]

        elif item == EItem.Stash:
            oid = Oid(hex=data)

            isStashHidden = False
            if index:  # in test mode, we may not have an index
                isStashHidden = self.model().data(index, ROLE_ISHIDDEN)

            actions += [
                TaskBook.action(ApplyStash, self.tr("&Apply"), taskArgs=oid),

                TaskBook.action(ExportStashAsPatch, self.tr("E&xport As Patch..."), taskArgs=oid),

                ActionDef.SEPARATOR,

                TaskBook.action(DropStash, self.tr("&Delete"), taskArgs=oid),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide in Graph"),
                          lambda: self.toggleHideStash.emit(oid),
                          checkState=1 if isStashHidden else -1,
                          statusTip=self.tr("Hide this stash from the graph")),
            ]

        elif item == EItem.TagsHeader:
            actions += [
                TaskBook.action(NewTag, self.tr("&New Tag on HEAD Commit...")),
            ]

        elif item == EItem.Tag:
            actions += [
                TaskBook.action(DeleteTag, self.tr("&Delete Tag"), taskArgs=data),
            ]

        elif item == EItem.Submodule:
            model: SidebarModel = self.model()
            repo = model.repo

            actions += [
                ActionDef(self.tr("&Open Submodule in New Tab"),
                          lambda: self.openSubmoduleRepo.emit(data)),

                ActionDef(self.tr("Open Submodule &Folder"),
                          lambda: self.openSubmoduleFolder.emit(data)),

                ActionDef(self.tr("Copy &Path"),
                          lambda: QApplication.clipboard().setText(os.path.join(repo.workdir, data))),
            ]

        # --------------------

        ActionDef.addToQMenu(menu, *actions)

        return menu

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)
        index: QModelIndex = self.indexAt(localPoint)
        if index.isValid():
            menu = self.generateMenuForEntry(*SidebarModel.unpackItemAndData(index), index=index)
            if menu.actions():
                menu.exec(globalPoint)
            menu.deleteLater()

    def refresh(self, repoState: RepoState):
        model: SidebarModel = self.model()
        model.refreshCache(repoState)
        self.restoreExpandedItems()

    def onEntryClicked(self, item: EItem, data: str):
        if item == EItem.UncommittedChanges:
            self.uncommittedChangesClicked.emit()
        elif item == EItem.UnbornHead:
            pass
        elif item == EItem.DetachedHead:
            self.refClicked.emit("HEAD")
        elif item == EItem.LocalBranch:
            self.refClicked.emit(RefPrefix.HEADS + data)
        elif item == EItem.RemoteBranch:
            self.refClicked.emit(RefPrefix.REMOTES + data)
        elif item == EItem.Tag:
            self.refClicked.emit(RefPrefix.TAGS + data)
        elif item == EItem.Stash:
            self.commitClicked.emit(Oid(hex=data))
        else:
            pass

    def onEntryDoubleClicked(self, item: EItem, data: str):
        if item == EItem.LocalBranch:
            SwitchBranch.invoke(data, True)  # True: ask for confirmation

        elif item == EItem.Remote:
            EditRemote.invoke(data)

        elif item == EItem.RemotesHeader:
            NewRemote.invoke()

        elif item == EItem.LocalBranchesHeader:
            NewBranchFromHead.invoke()

        elif item == EItem.UncommittedChanges:
            NewCommit.invoke()

        elif item == EItem.Submodule:
            self.openSubmoduleRepo.emit(data)

        elif item == EItem.StashesHeader:
            NewStash.invoke()

        elif item == EItem.Stash:
            oid = Oid(hex=data)
            ApplyStash.invoke(oid)

        elif item == EItem.RemoteBranch:
            NewTrackingBranch.invoke(data)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        if selected.count() == 0:
            return

        current = selected.indexes()[0]
        if not current.isValid():
            return

        unpacked = SidebarModel.unpackItemAndData(current)
        self.onEntryClicked(*unpacked)

    def mousePressEvent(self, event: QMouseEvent):
        index = self.indexAt(event.pos())
        rect = self.visualRect(index)
        if index.isValid() and rect.isValid() and event.pos().x() < rect.left():
            # Clicking collapse/expand triangle - will react in mouseReleaseEvent
            self.expandTriangleClickIndex = index
            event.accept()
        elif index.isValid():
            self.setCurrentIndex(index)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        index = self.indexAt(event.pos())
        rect = self.visualRect(index)
        if index.isValid() and rect.isValid() and event.pos().x() < rect.left() and index == self.expandTriangleClickIndex:
            # Let user collapse/expand in quick succession without triggering a double click
            self.eatDoubleClickTimer.restart()
            # Toggle expanded state
            item = SidebarModel.unpackItem(index)
            if item in ALWAYS_EXPAND or item in LEAF_ITEMS:
                pass
            elif self.isExpanded(index):
                self.collapse(index)
            else:
                self.expand(index)
            event.accept()
        else:
            self.expandTriangleClickIndex = None
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # NOT calling "super().mouseDoubleClickEvent(event)" on purpose.

        # See if we should drop this double click (see mouseReleaseEvent)
        eatTimer = self.eatDoubleClickTimer
        if eatTimer.isValid() and eatTimer.elapsed() < QApplication.doubleClickInterval():
            return
        eatTimer.invalidate()

        index: QModelIndex = self.indexAt(event.pos())
        if event.button() == Qt.MouseButton.LeftButton and index.isValid():
            self.onEntryDoubleClicked(*SidebarModel.unpackItemAndData(index))

    def indicesForItemType(self, item: EItem) -> list[QModelIndex]:
        """ Unit testing helper. Not efficient! """
        model: QAbstractItemModel = self.model()
        value = item.value
        indexList: list[QModelIndex] = model.match(model.index(0, 0), ROLE_EITEM, value, hits=-1, flags=Qt.MatchFlag.MatchRecursive)
        return indexList

    def datasForItemType(self, item: EItem, role: int = ROLE_USERDATA) -> list[str]:
        """ Unit testing helper. Not efficient! """
        model: QAbstractItemModel = self.model()
        indices = self.indicesForItemType(item)
        return [model.data(index, role) for index in indices]

    def indexForRef(self, ref: str) -> QModelIndex | None:
        model: QAbstractItemModel = self.model()

        index = model.match(model.index(0, 0), ROLE_REF, ref, hits=1,
                            flags=Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)

        if index:
            return index[0]
        else:
            return None

    def selectAnyRef(self, *refCandidates: str) -> QModelIndex | None:
        # Early out if any candidate ref is already selected
        with contextlib.suppress(IndexError):
            index = self.selectedIndexes()[0]
            if index and index.data(ROLE_REF) in refCandidates:
                return index

        # Find a visible index that matches any of the candidates
        for ref in refCandidates:
            index = self.indexForRef(ref)
            if index and self.isAncestryChainExpanded(index):  # Don't force-expand any collapsed indexes
                self.setCurrentIndex(index)
                return index

        # There are no indices that match the candidates, so select nothing
        self.clearSelection()
        return None

    def onExpanded(self, index: QModelIndex):
        h = SidebarModel.getCollapseHash(index)
        self.collapseCache.discard(h)

    def onCollapsed(self, index: QModelIndex):
        h = SidebarModel.getCollapseHash(index)
        self.collapseCache.add(h)

    @benchmark
    def restoreExpandedItems(self):
        # If we don't have a valid collapse cache (typically upon opening the repo), expand everything.
        # This can be pretty expensive, so cache collapsed items for next time.
        if not self.collapseCacheValid:
            self.expandAll()
            self.collapseCache.clear()
            self.collapseCacheValid = True
            return

        model: SidebarModel = self.model()

        frontier = [(0, model.index(row, 0)) for row in range(model.rowCount())]
        while frontier:
            depth, index = frontier.pop()
            item = SidebarModel.unpackItem(index)
            if item in LEAF_ITEMS:
                continue
            if item in ALWAYS_EXPAND:
                self.expand(index)
            else:
                h = SidebarModel.getCollapseHash(index)
                if h not in self.collapseCache:
                    self.expand(index)
            if item == EItem.RemotesHeader:  # Only RemotesHeader has children that can themselves be expanded
                for subrow in range(model.rowCount(index)):
                    frontier.append((depth+1, model.index(subrow, 0, index)))

    def isAncestryChainExpanded(self, index: QModelIndex):
        # Assume everything is expanded if collapse cache is missing (see restoreExpandedItems).
        if not self.collapseCacheValid:
            return True

        # My collapsed state doesn't matter here - it only affects my children.
        # So start looking at my parent.
        index = index.parent()

        # Walk up parent chain until root index (row -1)
        while index.row() >= 0:
            h = SidebarModel.getCollapseHash(index)
            if h in self.collapseCache:
                return False
            index = index.parent()

        return True

