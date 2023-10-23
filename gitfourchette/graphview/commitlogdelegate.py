from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.graphview.commitlogmodel import CommitLogModel
from gitfourchette.graphview.graphpaint import paintGraphFrame
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState, UC_FAKEID
from gitfourchette.toolbox import *
from dataclasses import dataclass
import contextlib
import pygit2
import traceback


@dataclass
class RefCallout:
    color: QColor
    keepPrefix: bool = False


CALLOUTS = {
    "refs/remotes/": RefCallout(QColor(Qt.GlobalColor.darkCyan)),
    "refs/tags/": RefCallout(QColor(Qt.GlobalColor.darkYellow)),
    "refs/heads/": RefCallout(QColor(Qt.GlobalColor.darkMagenta)),
    "stash@{": RefCallout(QColor(Qt.GlobalColor.darkGreen), keepPrefix=True),

    # detached HEAD as returned by porcelain.mapCommitsToReferences/getOidsForAllReferences
    "HEAD": RefCallout(QColor(Qt.GlobalColor.darkRed), keepPrefix=True),
}


ELISION = " […]"
ELISION_LENGTH = len(ELISION)


class CommitLogDelegate(QStyledItemDelegate):
    def __init__(self, repoWidget, parent=None):
        super().__init__(parent)
        self.repoWidget = repoWidget
        self.hashCharWidth = 0

        self.activeCommitFont = QFont()
        self.activeCommitFont.setBold(True)

        self.uncommittedFont = QFont()
        self.uncommittedFont.setItalic(True)

        self.smallFont = QFont()
        self.smallFont.setWeight(QFont.Weight.Light)
        self.smallFontMetrics = QFontMetricsF(self.smallFont)

    @property
    def state(self) -> RepoState:
        return self.repoWidget.state

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        try:
            self._paint(painter, option, index)
        except BaseException as exc:
            self._paintError(painter, option, index, exc)

    def _paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        hasFocus = option.state & QStyle.StateFlag.State_HasFocus
        isSelected = option.state & QStyle.StateFlag.State_Selected

        searchBar: SearchBar = self.parent().searchBar
        searchTerm = searchBar.searchTerm
        searchTermLooksLikeHash = searchBar.searchTermLooksLikeHash

        # Draw selection background _underneath_ the style's default graphics.
        # This is a workaround for the "windowsvista" style, which does not draw a solid color background for
        # selected items -- instead, it draws a very slight alpha overlay on _top_ of the item.
        # The problem is that its palette still returns white for foreground text, so the result would be unreadable
        # if we didn't draw a strong solid-color background. Most other styles draw their own background as a solid
        # color, so this rect is probably not visible outside of "windowsvista".
        if hasFocus and isSelected:
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))

        outlineColor = option.palette.color(QPalette.ColorRole.Base)

        super().paint(painter, option, index)

        XMargin = 4
        ColW_Hash = settings.prefs.shortHashChars + 1
        ColW_Date = 20
        if settings.prefs.authorDisplayStyle == AuthorDisplayStyle.INITIALS:
            ColW_Author = 8
        elif settings.prefs.authorDisplayStyle == AuthorDisplayStyle.FULL_NAME:
            ColW_Author = 20
        else:
            ColW_Author = 16

        painter.save()

        palette: QPalette = option.palette
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive

        if isSelected:
            #if option.state & QStyle.StateFlag.State_HasFocus:
            #    painter.fillRect(option.rect, palette.color(pcg, QPalette.ColorRole.Highlight))
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.HighlightedText))

        rect = QRect(option.rect)
        rect.setLeft(rect.left() + XMargin)
        rect.setRight(rect.right() - XMargin)

        # Get metrics of '0' before setting a custom font,
        # so that alignments are consistent in all commits regardless of bold or italic.
        if self.hashCharWidth == 0:
            self.hashCharWidth = max(painter.fontMetrics().horizontalAdvance(c) for c in "0123456789abcdef")

        commit: pygit2.Commit | None = index.data(CommitLogModel.CommitRole)
        if commit:
            oid = commit.oid
            # TODO: If is stash, getCoreStashMessage
            summaryText, contd = messageSummary(commit.message, ELISION)
            hashText = commit.oid.hex[:settings.prefs.shortHashChars]
            authorText = abbreviatePerson(commit.author, settings.prefs.authorDisplayStyle)

            qdt = QDateTime.fromSecsSinceEpoch(commit.author.time)
            dateText = self.repoWidget.locale().toString(qdt, settings.prefs.shortTimeFormat)
            if self.state.activeCommitOid == commit.oid:
                painter.setFont(self.activeCommitFont)
        else:
            oid = UC_FAKEID
            commit = None
            summaryText = self.tr("[Uncommitted Changes]")
            hashText = "·" * settings.prefs.shortHashChars
            authorText = ""
            dateText = ""
            painter.setFont(self.uncommittedFont)

            draftCommitMessage = self.state.getDraftCommitMessage()
            if draftCommitMessage:
                summaryText += F" {messageSummary(draftCommitMessage)[0]}"

        # Get metrics now so the message gets elided according to the custom font style
        # that may have been just set for this commit.
        metrics: QFontMetrics = painter.fontMetrics()

        # ------ Highlight searched hash
        if searchTerm and searchTermLooksLikeHash and commit and commit.hex.startswith(searchTerm):
            x1 = 0
            x2 = min(len(hashText), len(searchTerm)) * self.hashCharWidth
            if isSelected:
                painter.drawRect(rect.left()+x1, rect.top()+1, x2-x1, rect.height()-2)
            else:
                painter.fillRect(rect.left()+x1, rect.top(), x2-x1, rect.height(), colors.yellow)

        # ------ Hash
        rect.setWidth(ColW_Hash * self.hashCharWidth)
        charRect = QRect(rect.left(), rect.top(), self.hashCharWidth, rect.height())
        painter.save()
        if not isSelected:  # use muted color for hash if not selected
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.PlaceholderText))
        for hashChar in hashText:
            painter.drawText(charRect, Qt.AlignmentFlag.AlignCenter, hashChar)
            charRect.translate(self.hashCharWidth, 0)
        painter.restore()

        # ------ Graph
        rect.setLeft(rect.right())
        # if commit is not None:
        paintGraphFrame(self.state, oid, painter, rect, outlineColor)

        # ------ Callouts
        if oid in self.state.reverseRefCache:
            for refName in self.state.reverseRefCache[oid]:
                if refName != 'HEAD':
                    calloutText = refName
                    calloutColor = Qt.GlobalColor.darkMagenta
                elif self.state.headIsDetached:
                    calloutText = self.tr("detached HEAD")
                else:
                    continue

                for prefix in CALLOUTS:
                    if refName.startswith(prefix):
                        calloutDef = CALLOUTS[prefix]
                        if not calloutDef.keepPrefix:
                            calloutText = refName.removeprefix(prefix)
                        calloutColor = calloutDef.color
                        break

                painter.save()
                painter.setFont(self.smallFont)
                painter.setPen(calloutColor)
                rect.setLeft(rect.right())
                label = F"[{calloutText}] "
                rect.setWidth(int(self.smallFontMetrics.horizontalAdvance(label)))  # must be int for pyqt5 compat!
                painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, label)
                painter.restore()

        def elide(text):
            return metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())

        # ------ Message
        # use muted color for foreign commit messages if not selected
        if not isSelected and commit and commit.oid in self.state.foreignCommits:
            painter.setPen(Qt.GlobalColor.gray)
        rect.setLeft(rect.right())
        rect.setRight(option.rect.right() - (ColW_Author + ColW_Date) * self.hashCharWidth - XMargin)

        # ------ Highlight search term
        if searchTerm and commit and searchTerm in commit.message.lower():
            needleIndex = summaryText.lower().find(searchTerm)
            if needleIndex < 0:
                needleIndex = len(summaryText) - ELISION_LENGTH
                needleLength = ELISION_LENGTH
            else:
                needleLength = len(searchTerm)
            x1 = metrics.horizontalAdvance(summaryText, needleIndex)
            x2 = metrics.horizontalAdvance(summaryText, needleIndex + needleLength)
            if isSelected:
                painter.drawRect(rect.left()+x1, rect.top()+1, x2-x1, rect.height()-2)
            else:
                painter.fillRect(rect.left()+x1, rect.top(), x2-x1, rect.height(), colors.yellow)

        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(summaryText))

        # ------ Author
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Author * self.hashCharWidth)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(authorText))

        # ------ Date
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Date * self.hashCharWidth)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(dateText))

        # ----------------
        painter.restore()
        pass  # QStyledItemDelegate.paint(self, painter, option, index)

    def _paintError(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex, exc: BaseException):
        """Last-resort row drawing routine used if _paint raises an exception."""

        text = "?" * 7
        with contextlib.suppress(BaseException):
            commit: pygit2.Commit = index.data(CommitLogModel.CommitRole)
            text = commit.oid.hex[:7]
        with contextlib.suppress(BaseException):
            details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
            text += " " + shortenTracebackPath(details[-2].splitlines(False)[0]) + ":: " + repr(exc)

        if option.state & QStyle.StateFlag.State_Selected:
            bg, fg = Qt.GlobalColor.red, Qt.GlobalColor.white
        else:
            bg, fg = option.palette.color(QPalette.ColorRole.Base), Qt.GlobalColor.red

        painter.restore()
        painter.save()
        painter.fillRect(option.rect, bg)
        painter.setPen(fg)
        painter.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.SmallestReadableFont))
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        mult = settings.prefs.graph_rowHeight
        r = super().sizeHint(option, index)
        r.setHeight(option.fontMetrics.height() * mult // 100)
        return r
