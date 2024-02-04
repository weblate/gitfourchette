from contextlib import suppress
import logging

from gitfourchette import settings
from gitfourchette.nav import NavLocator
from gitfourchette.tasks import *
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.sidebar.sidebardelegate import SidebarDelegate
from gitfourchette.sidebar.sidebarmodel import (
    SidebarModel, SidebarNode, EItem,
    UNINDENT_ITEMS, LEAF_ITEMS, ALWAYS_EXPAND,
    ROLE_EITEM, ROLE_ISHIDDEN, ROLE_REF, ROLE_USERDATA,
)
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)


class Sidebar(QTreeView):
    jump = Signal(NavLocator)

    toggleHideStash = Signal(Oid)
    toggleHideBranch = Signal(str)
    toggleHideAllStashes = Signal()
    toggleHideRemote = Signal(str)

    pushBranch = Signal(str)

    openSubmoduleRepo = Signal(str)
    openSubmoduleFolder = Signal(str)

    statusMessage = Signal(str)

    @property
    def sidebarModel(self) -> SidebarModel:
        model = self.model()
        assert isinstance(model, SidebarModel)
        return model

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

        if settings.DEVDEBUG and QAbstractItemModelTester is not None:
            self.modelTester = QAbstractItemModelTester(self.model())
            logger.debug("ModelTester enabled. This will significantly slow down refreshes!")

        self.setAnimated(True)
        self.setUniformRowHeights(True)  # large sidebars update twice as fast with this, but we can't have thin spacers

        self.expanded.connect(self.onExpanded)
        self.collapsed.connect(self.onCollapsed)
        self.collapseCacheValid = False
        self.collapseCache = set()

        self.expandTriangleClickIndex = None
        self.eatDoubleClickTimer = QElapsedTimer()

        self.refreshPrefs()

    def switchMode(self, modeId: int):
        self.sidebarModel.switchMode(modeId)
        self.restoreExpandedItems()

    def visualRect(self, index: QModelIndex) -> QRect:
        """
        Required so the theme can properly draw unindented rows.
        TODO: Can we make it possible to click in blank space to select an item?
        """

        vr = super().visualRect(index)

        if index.isValid():
            node = SidebarNode.fromIndex(index)
            SidebarDelegate.unindentRect(node.kind, vr, self.indentation())

        return vr

    def updateHiddenBranches(self, hiddenBranches: list[str]):
        self.model().updateHiddenBranches(hiddenBranches)

    def generateMenuForEntry(self, item: EItem, data: str = "", menu: QMenu = None, index: QModelIndex = None):
        if menu is None:
            menu = QMenu(self)
            menu.setObjectName("SidebarContextMenu")

        actions = []

        model = self.sidebarModel
        repo = model.repo

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
            refName = data
            prefix, branchName = RefPrefix.split(data)
            assert prefix == RefPrefix.HEADS
            branch = repo.branches.local[branchName]

            activeBranchName = repo.head_branch_shorthand
            isCurrentBranch = branch and branch.is_checked_out()
            hasUpstream = bool(branch.upstream)
            upstreamBranchName = ""
            if branch.upstream:
                upstreamBranchName = branch.upstream.shorthand

            isBranchHidden = False
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)

            thisBranchDisplay = lquoe(branchName)
            activeBranchDisplay = lquoe(activeBranchName)
            upstreamBranchDisplay = lquoe(upstreamBranchName)

            actions += [
                TaskBook.action(
                    SwitchBranch,
                    self.tr("&Switch to {0}").format(thisBranchDisplay),
                    taskArgs=(data, False),  # False: don't ask for confirmation
                    enabled=not isCurrentBranch,
                ),

                ActionDef.SEPARATOR,

                TaskBook.action(
                    MergeBranch,
                    self.tr("&Merge into {0}...").format(activeBranchDisplay),
                    taskArgs=refName,
                    enabled=not isCurrentBranch and activeBranchName,
                ),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Push..."),
                          lambda: self.pushBranch.emit(branchName),
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
                    self.tr("Fast-Forward to {0}...").format(upstreamBranchDisplay) if upstreamBranchName else self.tr("Fast-Forward..."),
                    taskArgs=branchName,
                    enabled=hasUpstream,
                ),

                TaskBook.action(EditUpstreamBranch, self.tr("Set &Upstream Branch..."), taskArgs=branchName),

                ActionDef.SEPARATOR,

                TaskBook.action(RenameBranch, self.tr("Re&name..."), taskArgs=branchName),

                TaskBook.action(DeleteBranch, self.tr("&Delete..."), taskArgs=branchName),

                ActionDef.SEPARATOR,

                TaskBook.action(NewBranchFromRef, self.tr("New &Branch from Here..."), taskArgs=refName),

                ActionDef.SEPARATOR,

                ActionDef(
                    self.tr("&Hide in Graph"),
                    lambda: self.toggleHideBranch.emit(refName),
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

            activeBranchName = repo.head_branch_shorthand

            refName = data
            prefix, shorthand = RefPrefix.split(refName)
            assert prefix == RefPrefix.REMOTES
            thisBranchDisplay = lquoe(shorthand)
            activeBranchDisplay = lquoe(activeBranchName)

            actions += [
                TaskBook.action(
                    NewBranchFromRef,
                    self.tr("Start Local Branch from Here..."),
                    taskArgs=refName,
                ),

                TaskBook.action(FetchRemoteBranch, self.tr("Fetch Remote Changes..."), taskArgs=shorthand),

                ActionDef.SEPARATOR,

                TaskBook.action(
                    MergeBranch,
                    self.tr("&Merge into {0}...").format(activeBranchDisplay),
                    taskArgs=refName,
                ),

                ActionDef.SEPARATOR,

                TaskBook.action(RenameRemoteBranch, self.tr("Rename branch on remote..."), taskArgs=shorthand),

                TaskBook.action(DeleteRemoteBranch, self.tr("Delete branch on remote..."), taskArgs=shorthand),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide in Graph"),
                          lambda: self.toggleHideBranch.emit(refName),
                          checkState=1 if isBranchHidden else -1),
            ]

        elif item == EItem.Remote:
            actions += [
                TaskBook.action(EditRemote, self.tr("&Edit Remote..."), taskArgs=data),

                TaskBook.action(FetchRemote, self.tr("&Fetch All Remote Branches..."), taskArgs=data),

                ActionDef.SEPARATOR,

                TaskBook.action(DeleteRemote, self.tr("&Remove Remote..."), taskArgs=data),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide Remote in Graph"),
                          lambda: self.toggleHideRemote.emit(data),
                          checkState=1 if data in model._hiddenRemotes else -1,
                          ),
            ]

        elif item == EItem.RemotesHeader:
            actions += [
                TaskBook.action(NewRemote, "&A"),
            ]

        elif item == EItem.StashesHeader:
            actions += [
                TaskBook.action(NewStash, "&S"),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("&Hide All Stashes in Graph"),
                          lambda: self.toggleHideAllStashes.emit(),
                          checkState=1 if model._hideAllStashes else -1,
                          ),
            ]

        elif item == EItem.Stash:
            oid = Oid(hex=data)

            isStashHidden = False
            if index:  # in test mode, we may not have an index
                isStashHidden = model.data(index, ROLE_ISHIDDEN)

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
            model = self.sidebarModel
            repo = model.repo

            actions += [
                ActionDef(self.tr("&Open Submodule in New Tab"),
                          lambda: self.openSubmoduleRepo.emit(data)),

                ActionDef(self.tr("Open Submodule &Folder"),
                          lambda: self.openSubmoduleFolder.emit(data)),

                ActionDef(self.tr("Copy &Path"),
                          lambda: self.copyToClipboard(repo.in_workdir(data)))
            ]

        # --------------------

        ActionDef.addToQMenu(menu, *actions)

        return menu

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)
        index: QModelIndex = self.indexAt(localPoint)
        if index.isValid():
            node = SidebarNode.fromIndex(index)
            menu = self.generateMenuForEntry(node.kind, node.data, index=index)
            if menu.actions():
                menu.exec(globalPoint)
            menu.deleteLater()

    def refresh(self, repoState: RepoState):
        self.sidebarModel.refreshCache(repoState)
        self.restoreExpandedItems()

    def refreshPrefs(self):
        self.setVerticalScrollMode(settings.prefs.listViewScrollMode)

    def wantSelectNode(self, node: SidebarNode):
        if node is None:
            return
        assert isinstance(node, SidebarNode)

        item = node.kind

        if item == EItem.UncommittedChanges:
            locator = NavLocator.inWorkdir()
        elif item == EItem.UnbornHead:
            locator = NavLocator.inWorkdir()
        elif item == EItem.DetachedHead:
            locator = NavLocator.inRef("HEAD")
        elif item == EItem.LocalBranch:
            locator = NavLocator.inRef(node.data)
        elif item == EItem.RemoteBranch:
            locator = NavLocator.inRef(node.data)
        elif item == EItem.Tag:
            locator = NavLocator.inRef(node.data)
        elif item == EItem.Stash:
            locator = NavLocator.inCommit(Oid(hex=node.data))
        else:
            return None

        self.jump.emit(locator)

    def wantEnterNode(self, node: SidebarNode):
        if node is None:
            QApplication.beep()
            return
        assert isinstance(node, SidebarNode)

        item = node.kind

        if item == EItem.Spacer:
            pass

        elif item == EItem.LocalBranch:
            SwitchBranch.invoke(node.data.removeprefix(RefPrefix.HEADS), True)  # True: ask for confirmation

        elif item == EItem.Remote:
            EditRemote.invoke(node.data)

        elif item == EItem.RemotesHeader:
            NewRemote.invoke()

        elif item == EItem.LocalBranchesHeader:
            NewBranchFromHead.invoke()

        elif item == EItem.UncommittedChanges:
            NewCommit.invoke()

        elif item == EItem.Submodule:
            self.openSubmoduleRepo.emit(node.data)

        elif item == EItem.StashesHeader:
            NewStash.invoke()

        elif item == EItem.Stash:
            oid = Oid(hex=node.data)
            ApplyStash.invoke(oid)

        elif item == EItem.RemoteBranch:
            NewBranchFromRef.invoke(node.data)

        elif item == EItem.TagsHeader:
            NewTag.invoke()

        else:
            QApplication.beep()

    def wantDeleteNode(self, node: SidebarNode):
        if node is None:
            QApplication.beep()
            return

        item = node.kind
        data = node.data

        if item == EItem.Spacer:
            pass

        elif item == EItem.LocalBranch:
            DeleteBranch.invoke(data.removeprefix(RefPrefix.HEADS))

        elif item == EItem.Remote:
            DeleteRemote.invoke(data)

        elif item == EItem.Stash:
            oid = Oid(hex=data)
            DropStash.invoke(oid)

        elif item == EItem.RemoteBranch:
            DeleteRemoteBranch.invoke(data)

        elif item == EItem.Tag:
            DeleteTag.invoke(data.removeprefix(RefPrefix.TAGS))

        else:
            QApplication.beep()

    def wantRenameNode(self, node: SidebarNode):
        if node is None:
            QApplication.beep()
            return

        item = node.kind
        data = node.data

        if item == EItem.Spacer:
            pass

        elif item == EItem.LocalBranch:
            RenameBranch.invoke(data)

        elif item == EItem.Remote:
            EditRemote.invoke(data)

        elif item == EItem.RemoteBranch:
            RenameRemoteBranch.invoke(data)

        else:
            QApplication.beep()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()

        def getValidNode():
            try:
                index: QModelIndex = self.selectedIndexes()[0]
                return SidebarNode.fromIndex(index)
            except IndexError:
                return None

        if k in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.wantEnterNode(getValidNode())

        elif k in [Qt.Key.Key_Delete]:
            self.wantDeleteNode(getValidNode())

        elif k in [Qt.Key.Key_F2]:
            self.wantRenameNode(getValidNode())

        else:
            super().keyPressEvent(event)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        if selected.count() == 0:
            return

        current = selected.indexes()[0]
        if not current.isValid():
            return

        self.wantSelectNode(SidebarNode.fromIndex(current))

    def clickFallsInExpandTriangle(self, index, x):
        if not index.isValid():
            return False

        rect = self.visualRect(index)
        if not rect.isValid():
            return False

        if self.isLeftToRight():
            return x < rect.left()
        else:
            return x > rect.right()

    def mousePressEvent(self, event: QMouseEvent):
        index = self.indexAt(event.pos())
        if self.clickFallsInExpandTriangle(index, event.pos().x()):
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
        if self.clickFallsInExpandTriangle(index, event.pos().x()):
            # Let user collapse/expand in quick succession without triggering a double click
            self.eatDoubleClickTimer.restart()
            # Toggle expanded state
            assert index.isValid()
            if SidebarNode.fromIndex(index).kind in (ALWAYS_EXPAND, LEAF_ITEMS):
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
            self.wantEnterNode(SidebarNode.fromIndex(index))

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
        with suppress(IndexError):
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

        model = self.sidebarModel

        frontier = [(0, model.index(row, 0)) for row in range(model.rowCount(QModelIndex()))]
        while frontier:
            depth, index = frontier.pop()
            node = SidebarNode.fromIndex(index)

            if node.kind in LEAF_ITEMS:
                continue

            if node.kind in ALWAYS_EXPAND:
                self.expand(index)
            else:
                h = SidebarModel.getCollapseHash(index)
                if h not in self.collapseCache:
                    self.expand(index)

            if node.kind == EItem.RemotesHeader:  # Only RemotesHeader has children that can themselves be expanded
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

    def copyToClipboard(self, text: str):
        QApplication.clipboard().setText(text),
        self.statusMessage.emit(clipboardStatusMessage(text))
