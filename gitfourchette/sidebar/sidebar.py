import contextlib

import pygit2

from gitfourchette import porcelain
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.sidebar.sidebardelegate import SidebarDelegate
from gitfourchette.sidebar.sidebarmodel import (SidebarModel, EItem, UNINDENT_ITEMS, ROLE_EITEM, ROLE_ISHIDDEN,
                                                ROLE_REF, ROLE_USERDATA)
from gitfourchette.toolbox import *


class Sidebar(QTreeView):
    uncommittedChangesClicked = Signal()
    refClicked = Signal(str)
    commitClicked = Signal(pygit2.Oid)

    newBranch = Signal()
    newBranchFromLocalBranch = Signal(str)
    renameBranch = Signal(str)
    deleteBranch = Signal(str)
    switchToBranch = Signal(str, bool)  # bool: ask for confirmation before switching
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    pushBranch = Signal(str)
    fastForwardBranch = Signal(str)
    toggleHideBranch = Signal(str)
    newTrackingBranch = Signal(str)
    fetchRemoteBranch = Signal(str)
    renameRemoteBranch = Signal(str)
    deleteRemoteBranch = Signal(str)
    editTrackingBranch = Signal(str)
    commitChanges = Signal()
    amendChanges = Signal()
    exportWorkdirAsPatch = Signal()

    newRemote = Signal()
    fetchRemote = Signal(str)
    editRemote = Signal(str)
    deleteRemote = Signal(str)

    newStash = Signal()
    applyStash = Signal(pygit2.Oid)
    exportStashAsPatch = Signal(pygit2.Oid)
    dropStash = Signal(pygit2.Oid)

    newTag = Signal()
    deleteTag = Signal(str)

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

    def visualRect(self, index):
        """Required so the theme can properly draw unindented rows.
        The offset should match that in SidebarDelegate."""

        vr = super().visualRect(index)

        with contextlib.suppress(ValueError):
            item = SidebarModel.unpackItem(index)

            if item in UNINDENT_ITEMS:
                vr.adjust(-self.indentation(), 0, 0, 0)

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
                ActionDef(self.tr("&Commit Staged Changes..."), self.commitChanges, shortcuts=GlobalShortcuts.commit),
                ActionDef(self.tr("&Amend Last Commit..."), self.amendChanges, shortcuts=GlobalShortcuts.amendCommit),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("&Stash Uncommitted Changes..."), self.newStash, shortcuts=GlobalShortcuts.newStash),
                ActionDef(self.tr("E&xport Uncommitted Changes As Patch..."), self.exportWorkdirAsPatch),
            ]

        elif item == EItem.LocalBranchesHeader:
            actions += [
                ActionDef(self.tr("&New Branch..."), lambda: self.newBranch.emit(), shortcuts=GlobalShortcuts.newBranch),
            ]

        elif item == EItem.LocalBranch:
            fontMetrics = menu.fontMetrics()

            model: SidebarModel = self.model()
            repo = model.repo
            branch = repo.branches.local[data]

            activeBranchName = porcelain.getActiveBranchShorthand(repo)
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
                ActionDef(self.tr("&Switch to “{0}”").format(thisBranchDisplay),
                          lambda: self.switchToBranch.emit(data, False),  # False: don't ask for confirmation
                          "document-swap",
                          enabled=not isCurrentBranch),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Merge “{0}” into “{1}”...").format(thisBranchDisplay, activeBranchDisplay),
                          lambda: self.mergeBranchIntoActive.emit(data),
                          enabled=not isCurrentBranch and activeBranchName),

                ActionDef(self.tr("&Rebase “{0}” onto “{1}”...").format(activeBranchDisplay, thisBranchDisplay),
                          lambda: self.rebaseActiveOntoBranch.emit(data),
                          enabled=not isCurrentBranch and activeBranchName),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Push..."),
                          lambda: self.pushBranch.emit(data),
                          "vcs-push",
                          shortcuts=GlobalShortcuts.pushBranch),

                ActionDef(self.tr("&Fetch..."),
                          lambda: self.fetchRemoteBranch.emit(branch.upstream.shorthand),
                          QStyle.StandardPixmap.SP_BrowserReload,
                          enabled=hasUpstream),

                ActionDef(self.tr("Fast-Forward to “{0}”...").format(upstreamBranchDisplay)
                          if upstreamBranchName else self.tr("Fast-Forward..."),
                          lambda: self.fastForwardBranch.emit(data),
                          "vcs-pull",
                          enabled=hasUpstream,
                          shortcuts=GlobalShortcuts.pullBranch),

                ActionDef(self.tr("Set &Tracked Branch..."),
                          lambda: self.editTrackingBranch.emit(data)),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("Re&name..."),
                          lambda: self.renameBranch.emit(data)),

                ActionDef(self.tr("&Delete..."),
                          lambda: self.deleteBranch.emit(data),
                          "vcs-branch-delete"),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("New &Branch from Here..."),
                          lambda: self.newBranchFromLocalBranch.emit(data),
                          "vcs-branch"),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide in graph"),
                          lambda: self.toggleHideBranch.emit("refs/heads/" + data),
                          checkState=1 if isBranchHidden else -1),
            ]

        elif item == EItem.DetachedHead:
            actions += [
                ActionDef(self.tr("New &Branch from Here..."),
                          lambda: self.newBranch.emit(),
                          "vcs-branch",
                          shortcuts=GlobalShortcuts.newBranch),
            ]

        elif item == EItem.RemoteBranch:
            isBranchHidden = False
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)

            actions += [
                ActionDef(self.tr("New local branch tracking “{0}”...").format(escamp(elide(data))),
                          lambda: self.newTrackingBranch.emit(data),
                          "vcs-branch"),

                ActionDef(self.tr("Fetch this remote branch..."),
                          lambda: self.fetchRemoteBranch.emit(data),
                          QStyle.StandardPixmap.SP_BrowserReload),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("Rename branch on remote..."),
                          lambda: self.renameRemoteBranch.emit(data)),

                ActionDef(self.tr("Delete branch on remote..."),
                          lambda: self.deleteRemoteBranch.emit(data),
                          QStyle.StandardPixmap.SP_TrashIcon),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide in graph"),
                          lambda: self.toggleHideBranch.emit("refs/remotes/" + data),
                          checkState=1 if isBranchHidden else -1),
            ]

        elif item == EItem.Remote:
            actions += [
                ActionDef(self.tr("&Edit Remote..."),
                          lambda: self.editRemote.emit(data),
                          "document-edit"),

                ActionDef(self.tr("&Fetch all branches on this remote..."),
                          lambda: self.fetchRemote.emit(data),
                          QStyle.StandardPixmap.SP_BrowserReload),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Remove Remote..."),
                          lambda: self.deleteRemote.emit(data),
                          QStyle.StandardPixmap.SP_TrashIcon),
            ]

        elif item == EItem.RemotesHeader:
            actions += [
                ActionDef(self.tr("&Add Remote..."),
                          self.newRemote),
            ]

        elif item == EItem.StashesHeader:
            actions += [
                ActionDef(self.tr("&New Stash..."),
                          self.newStash,
                          shortcuts=GlobalShortcuts.newStash),
            ]

        elif item == EItem.Stash:
            oid = pygit2.Oid(hex=data)

            actions += [
                ActionDef(self.tr("&Apply"),
                          lambda: self.applyStash.emit(oid)),

                ActionDef(self.tr("E&xport As Patch..."),
                          lambda: self.exportStashAsPatch.emit(oid)),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Delete"),
                          lambda: self.dropStash.emit(oid),
                          QStyle.StandardPixmap.SP_TrashIcon),
            ]

        elif item == EItem.TagsHeader:
            actions += [
                ActionDef(self.tr("&New Tag on HEAD Commit..."),
                          self.newTag, ),
            ]

        elif item == EItem.Tag:
            actions += [
                ActionDef(self.tr("&Delete"),
                          lambda: self.deleteTag.emit(data),
                          icon=QStyle.StandardPixmap.SP_TrashIcon),
            ]

        elif item == EItem.Submodule:
            actions += [
                ActionDef(self.tr("&Open submodule in {0}").format(qAppName()),
                          lambda: self.openSubmoduleRepo.emit(data)),

                ActionDef(self.tr("Open submodule &folder"),
                          lambda: self.openSubmoduleFolder.emit(data)),
            ]

        # --------------------

        ActionDef.addToQMenu(menu, actions)

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
        sidebarModel: SidebarModel = self.model()
        sidebarModel.refreshCache(repoState.repo, repoState.hiddenBranches, repoState.refCache)
        self.expandAll()

    def onEntryClicked(self, item: EItem, data: str):
        if item == EItem.UncommittedChanges:
            self.uncommittedChangesClicked.emit()
        elif item == EItem.UnbornHead:
            pass
        elif item == EItem.DetachedHead:
            self.refClicked.emit("HEAD")
        elif item == EItem.LocalBranch:
            self.refClicked.emit(porcelain.HEADS_PREFIX + data)
        elif item == EItem.RemoteBranch:
            self.refClicked.emit(porcelain.REMOTES_PREFIX + data)
        elif item == EItem.Tag:
            self.refClicked.emit(porcelain.TAGS_PREFIX + data)
        elif item == EItem.Stash:
            self.commitClicked.emit(pygit2.Oid(hex=data))
        else:
            pass

    def onEntryDoubleClicked(self, item: EItem, data: str):
        if item == EItem.LocalBranch:
            self.switchToBranch.emit(data, True)  # ask for confirmation
        elif item == EItem.Remote:
            self.editRemote.emit(data)
        elif item == EItem.RemotesHeader:
            self.newRemote.emit()
        elif item == EItem.LocalBranchesHeader:
            self.newBranch.emit()
        elif item == EItem.UncommittedChanges:
            self.commitChanges.emit()
        elif item == EItem.Submodule:
            self.openSubmoduleRepo.emit(data)
        elif item == EItem.StashesHeader:
            self.newStash.emit()
        elif item == EItem.Stash:
            oid = pygit2.Oid(hex=data)
            self.applyStash.emit(oid)
        elif item == EItem.RemoteBranch:
            self.newTrackingBranch.emit(data)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super().currentChanged(current, previous)
        if current.isValid():
            self.onEntryClicked(*SidebarModel.unpackItemAndData(current))

    def mouseDoubleClickEvent(self, event):
        # NOT calling "super().mouseDoubleClickEvent(event)" on purpose.
        index: QModelIndex = self.indexAt(event.pos())
        if event.button() == Qt.MouseButton.LeftButton and index.isValid():
            self.onEntryDoubleClicked(*SidebarModel.unpackItemAndData(index))

    def indicesForItemType(self, item: EItem) -> list[QModelIndex]:
        """ Unit testing helper """
        model: QAbstractItemModel = self.model()
        value = item.value
        indexList: list[QModelIndex] = model.match(model.index(0, 0), ROLE_EITEM, value, hits=-1, flags=Qt.MatchFlag.MatchRecursive)
        return indexList

    def datasForItemType(self, item: EItem, role: int = ROLE_USERDATA) -> list[str]:
        """ Unit testing helper """
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
            currentIndex = self.selectedIndexes()[0]
            if currentIndex and currentIndex.data(ROLE_REF) in refCandidates:
                return currentIndex

        # Find an index that matches any of the candidates
        for ref in refCandidates:
            index = self.indexForRef(ref)
            if index:
                self.setCurrentIndex(index)
                return index

        # There are no indices that match the candidates, so select nothing
        self.clearSelection()
        return None
