import porcelain
from allqt import *
from util import labelQuote, shortHash
from dataclasses import dataclass
from typing import Any
import pygit2
import enum


class SidebarEntryType(enum.Enum):
    UNCOMMITTED_CHANGES = enum.auto()
    LOCAL_BRANCHES_HEADER = enum.auto()
    LOCAL_BRANCH = enum.auto()
    DETACHED_HEAD = enum.auto()
    UNBORN_HEAD = enum.auto()
    REMOTE_BRANCH = enum.auto()
    REMOTE = enum.auto()
    TAG = enum.auto()


@dataclass
class SidebarEntry:
    type: SidebarEntryType
    data: str = None


# TODO: we should just use a custom model
def SidebarItem(name: str, data=None) -> QStandardItem:
    item = QStandardItem(name)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if data:
        item.setData(data, Qt.UserRole)
    item.setSizeHint(QSize(-1, 16))
    return item


def SidebarSeparator() -> QStandardItem:
    sep = SidebarItem(None)
    sep.setSelectable(False)
    sep.setEnabled(False)
    sep.setSizeHint(QSize(-1, 8))
    return sep


class SidebarDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        view: QTreeView = self.parent()
        model: QStandardItemModel = index.model()

        opt = QStyleOptionViewItem(option)
        opt.rect.setLeft(20)

        if not index.parent().isValid():
            opt.font = QFont()
            opt.font.setBold(True)

        super().paint(painter, opt, index)

        if model.rowCount(index) > 0:
            opt = QStyleOptionViewItem(option)
            opt.rect.setLeft(0)
            opt.rect.setRight(20)

            style: QStyle = view.style()
            arrowPrimitive = QStyle.PE_IndicatorArrowDown if view.isExpanded(index) else QStyle.PE_IndicatorArrowRight
            style.drawPrimitive(arrowPrimitive, opt, painter, view)


class Sidebar(QTreeView):
    uncommittedChangesClicked = Signal()
    refClicked = Signal(str)

    newBranch = Signal()
    renameBranch = Signal(str)
    deleteBranch = Signal(str)
    switchToBranch = Signal(str)
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    pushBranch = Signal(str)
    newTrackingBranch = Signal(str)
    editTrackingBranch = Signal(str)

    editRemote = Signal(str)
    deleteRemote = Signal(str)

    repo: pygit2.Repository

    def __init__(self, parent):
        super().__init__(parent)

        self.setMinimumWidth(128)

        self.repo = None

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        #self.setUniformRowHeights(True)
        self.setHeaderHidden(True)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

        self.setObjectName("sidebar")  # for styling

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setItemDelegate(SidebarDelegate(self))

    def generateMenuForEntry(self, entryType: SidebarEntryType, data: str = "", menu: QMenu = None):
        if menu is None:
            menu = QMenu(self)
            menu.setObjectName("SidebarContextMenu")

        if entryType == SidebarEntryType.LOCAL_BRANCHES_HEADER:
            menu.addAction(F"&New Branch...", lambda: self.newBranch.emit())

        elif entryType == SidebarEntryType.LOCAL_BRANCH:
            branch: pygit2.Branch = self.repo.branches.local[data]

            activeBranchName = porcelain.getActiveBranchShorthand(self.repo)

            switchAction: QAction = menu.addAction(F"&Switch to {labelQuote(data)}")
            menu.addSeparator()
            mergeAction: QAction = menu.addAction(F"&Merge {labelQuote(data)} into {labelQuote(activeBranchName)}...")
            rebaseAction: QAction = menu.addAction(F"&Rebase {labelQuote(activeBranchName)} onto {labelQuote(data)}...")

            switchAction.setIcon(QIcon.fromTheme("document-swap"))

            for action in switchAction, mergeAction, rebaseAction:
                action.setEnabled(False)

            if branch and not branch.is_checked_out():
                switchAction.triggered.connect(lambda: self.switchToBranch.emit(data))
                switchAction.setEnabled(True)

                if activeBranchName:
                    mergeAction.triggered.connect(lambda: self.mergeBranchIntoActive.emit(data))
                    rebaseAction.triggered.connect(lambda: self.rebaseActiveOntoBranch.emit(data))

                    mergeAction.setEnabled(True)
                    rebaseAction.setEnabled(True)

            menu.addSeparator()

            if branch.upstream:
                a = menu.addAction(F"&Push to {labelQuote(branch.upstream.shorthand)}...",
                                   lambda: self.pushBranch.emit(data))
                a.setIcon(QIcon.fromTheme("vcs-push"))
            else:
                a = menu.addAction("&Push: no tracked branch")
                a.setEnabled(False)
                a.setIcon(QIcon.fromTheme("vcs-push"))

            menu.addAction("Set &Tracked Branch...", lambda: self.editTrackingBranch.emit(data))

            menu.addSeparator()

            menu.addAction("Re&name...", lambda: self.renameBranch.emit(data))
            a = menu.addAction("&Delete...", lambda: self.deleteBranch.emit(data))
            a.setIcon(QIcon.fromTheme("vcs-branch-delete"))

        elif entryType == SidebarEntryType.REMOTE_BRANCH:
            menu.addAction(F"New local branch tracking {labelQuote(data)}...",
                           lambda: self.newTrackingBranch.emit(data))

        elif entryType == SidebarEntryType.REMOTE:
            a = menu.addAction(F"Edit Remote...", lambda: self.editRemote.emit(data))
            a.setIcon(QIcon.fromTheme("document-edit"))

            menu.addSeparator()

            a = menu.addAction(F"Delete Remote", lambda: self.deleteRemote.emit(data))
            a.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))

        return menu

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)
        index = self.indexAt(localPoint)
        entry: SidebarEntry = index.data(Qt.UserRole)

        if entry:
            menu = self.generateMenuForEntry(entry.type, entry.data)
            menu.exec_(globalPoint)

    def fill(self, repo: pygit2.Repository):
        model = QStandardItemModel()

        uncommittedChangesEntry = SidebarEntry(SidebarEntryType.UNCOMMITTED_CHANGES)
        uncommittedChanges = SidebarItem("Changes", uncommittedChangesEntry)
        model.appendRow(uncommittedChanges)

        model.appendRow(SidebarSeparator())

        branchesParentEntry = SidebarEntry(SidebarEntryType.LOCAL_BRANCHES_HEADER)
        branchesParent = SidebarItem("Local Branches", branchesParentEntry)
        branchesParent.setSelectable(False)

        if repo.head_is_unborn:
            target: str = repo.lookup_reference("HEAD").target
            target = target.removeprefix("refs/heads/")
            caption = F"★ {target} (unborn)"
            branchEntry = SidebarEntry(SidebarEntryType.UNBORN_HEAD)
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(F"Unborn HEAD (does not point to a commit yet)")
            branchesParent.appendRow(item)
        elif repo.head_is_detached:
            caption = F"★ detached HEAD @ {shortHash(repo.head.target)}"
            branchEntry = SidebarEntry(SidebarEntryType.DETACHED_HEAD, str(repo.head.target))#repo.head.target)
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(F"detached HEAD @{shortHash(repo.head.target)}")
            branchesParent.appendRow(item)

        for localBranch in repo.branches.local:
            branch = repo.branches[localBranch]
            caption = branch.branch_name
            tooltip = branch.branch_name
            if not repo.head_is_detached and branch.is_checked_out():
                caption = F"★ {caption}"
                tooltip += " (★ active branch)"
            branchEntry = SidebarEntry(SidebarEntryType.LOCAL_BRANCH, branch.branch_name)
            if branch.upstream:
                branchEntry.trackingBranch = branch.upstream.branch_name
                tooltip += F"\ntracking remote {branchEntry.trackingBranch}"
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(tooltip)
            branchesParent.appendRow(item)

        model.appendRow(branchesParent)

        model.appendRow(SidebarSeparator())

        for remoteName, remoteBranches in porcelain.getRemoteBranchNames(repo).items():
            remoteEntry = SidebarEntry(SidebarEntryType.REMOTE, remoteName)
            remoteParent = SidebarItem(F"Remote “{remoteName}”", remoteEntry)
            remoteParent.setSelectable(False)

            for remoteBranch in sorted(remoteBranches):
                remoteRefEntry = SidebarEntry(SidebarEntryType.REMOTE_BRANCH, F"{remoteName}/{remoteBranch}")
                remoteRefItem = SidebarItem(remoteBranch, remoteRefEntry)
                remoteParent.appendRow(remoteRefItem)

            model.appendRow(remoteParent)
            model.appendRow(SidebarSeparator())

        tagsParent = QStandardItem("Tags")
        tagsParent.setSelectable(False)
        for name in porcelain.getTagNames(repo):
            tagEntry = SidebarEntry(SidebarEntryType.TAG, name)
            tagItem = SidebarItem(name, tagEntry)
            tagsParent.appendRow(tagItem)
        model.appendRow(tagsParent)

        self.repo = repo
        self._replaceModel(model)

        # expand branch container
        self.setExpanded(model.indexFromItem(branchesParent), True)

    def _replaceModel(self, model):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        self.setModel(model)

    def onEntryClicked(self, entryType: SidebarEntryType, data: str):
        if entryType == SidebarEntryType.UNCOMMITTED_CHANGES:
            self.uncommittedChangesClicked.emit()
        elif entryType == SidebarEntryType.UNBORN_HEAD:
            pass
        elif entryType == SidebarEntryType.DETACHED_HEAD:
            self.refClicked.emit("HEAD")
        elif entryType == SidebarEntryType.LOCAL_BRANCH:
            self.refClicked.emit(F"refs/heads/{data}")
        elif entryType == SidebarEntryType.REMOTE_BRANCH:
            self.refClicked.emit(F"refs/remotes/{data}")
        elif entryType == SidebarEntryType.TAG:
            self.refClicked.emit(F"refs/tags/{data}")
        else:
            print("Unsupported sidebar entry type", entryType)

    def onEntryDoubleClicked(self, entryType: SidebarEntryType, data: Any):
        if entryType == SidebarEntryType.LOCAL_BRANCH:
            self.switchToBranch.emit(data)
        elif entryType == SidebarEntryType.REMOTE:
            self.editRemoteFlow.emit(data)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super().currentChanged(current, previous)
        if not current.isValid():
            return
        entry: SidebarEntry = current.data(Qt.UserRole)
        if entry:
            self.onEntryClicked(entry.type, entry.data)

    def mouseDoubleClickEvent(self, event):
        index: QModelIndex = self.indexAt(event.pos())
        if event.button() == Qt.LeftButton and index.isValid():
            entry: SidebarEntry = index.data(Qt.UserRole)
            if entry:
                self.onEntryDoubleClicked(entry.type, entry.data)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        index: QModelIndex = self.indexAt(event.pos())
        lastState = self.isExpanded(index)
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton and index.isValid() and lastState == self.isExpanded(index):
            self.setExpanded(index, not lastState)
