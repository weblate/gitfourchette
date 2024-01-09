from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.appconsts import ACTIVE_BULLET
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.graphview.commitlogmodel import CommitLogModel
from gitfourchette.graphview.graphpaint import paintGraphFrame
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState, UC_FAKEID
from gitfourchette.toolbox import *
from dataclasses import dataclass
import contextlib
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

    # detached HEAD as returned by Repo.map_commits_to_refs
    "HEAD": RefCallout(QColor(Qt.GlobalColor.darkRed), keepPrefix=True),
}


ELISION = " […]"
ELISION_LENGTH = len(ELISION)


MAX_AUTHOR_CHARS = {
    AuthorDisplayStyle.INITIALS: 7,
    AuthorDisplayStyle.FULL_NAME: 20,
}


XMARGIN = 4
XSPACING = 6


class CommitLogDelegate(QStyledItemDelegate):
    def __init__(self, repoWidget, parent=None):
        super().__init__(parent)

        self.repoWidget = repoWidget

        self.mustRefreshMetrics = True
        self.hashCharWidth = 0
        self.dateMaxWidth = 0
        self.activeCommitFont = QFont()
        self.uncommittedFont = QFont()
        self.calloutFont = QFont()
        self.calloutFontMetrics = QFontMetricsF(self.calloutFont)
        self.activeCalloutFont = QFont()
        self.activeCalloutFontMetrics = QFontMetricsF(self.activeCalloutFont)

    def invalidateMetrics(self):
        self.mustRefreshMetrics = True

    def refreshMetrics(self, option: QStyleOptionViewItem):
        if not self.mustRefreshMetrics:
            return

        self.mustRefreshMetrics = False

        self.hashCharWidth = max(option.fontMetrics.horizontalAdvance(c) for c in "0123456789abcdef")

        self.activeCommitFont = QFont(option.font)
        self.activeCommitFont.setBold(True)

        self.uncommittedFont = QFont(option.font)
        self.uncommittedFont.setItalic(True)

        self.calloutFont = QFont(option.font)
        self.calloutFont.setWeight(QFont.Weight.Light)
        self.calloutFontMetrics = QFontMetricsF(self.calloutFont)

        self.activeCalloutFont = QFont(self.calloutFont)
        self.activeCalloutFont.setWeight(QFont.Weight.Bold)
        self.activeCalloutFontMetrics = QFontMetricsF(self.activeCalloutFont)

        wideDate = QDateTime.fromString("2999-12-25T23:59:59.999", Qt.DateFormat.ISODate)
        dateText = option.locale.toString(wideDate, settings.prefs.shortTimeFormat)
        self.dateMaxWidth = QFontMetrics(self.activeCommitFont).horizontalAdvance(dateText + " ")
        self.dateMaxWidth = int(self.dateMaxWidth)  # make sure it's an int for pyqt5 compat

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

        # Draw selection background _underneath_ the style's default graphics.
        # This is a workaround for the "windowsvista" style, which does not draw a solid color background for
        # selected items -- instead, it draws a very slight alpha overlay on _top_ of the item.
        # The problem is that its palette still returns white for foreground text, so the result would be unreadable
        # if we didn't draw a strong solid-color background. Most other styles draw their own background as a solid
        # color, so this rect is probably not visible outside of "windowsvista".
        if hasFocus and isSelected:
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))

        outlineColor = option.palette.color(QPalette.ColorRole.Base)

        # Draw default background
        super().paint(painter, option, index)

        painter.save()

        palette: QPalette = option.palette
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive

        if isSelected:
            #if option.state & QStyle.StateFlag.State_HasFocus:
            #    painter.fillRect(option.rect, palette.color(pcg, QPalette.ColorRole.Highlight))
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.HighlightedText))

        # Get metrics of '0' before setting a custom font,
        # so that alignments are consistent in all commits regardless of bold or italic.
        self.refreshMetrics(option)
        hcw = self.hashCharWidth

        # Set up rect
        rect = QRect(option.rect)
        rect.setLeft(rect.left() + XMARGIN)
        rect.setRight(rect.right() - XMARGIN)

        # Compute column bounds
        leftBoundHash = rect.left()
        leftBoundSummary = leftBoundHash + hcw * settings.prefs.shortHashChars + XSPACING
        leftBoundDate = rect.width() - self.dateMaxWidth
        leftBoundName = leftBoundDate - hcw * MAX_AUTHOR_CHARS.get(settings.prefs.authorDisplayStyle, 16)
        rightBound = rect.right()

        # Get the info we need about the commit
        commit: Commit | None = index.data(CommitLogModel.CommitRole)
        if commit:
            oid = commit.oid
            # TODO: If is stash, getCoreStashMessage
            summaryText, contd = messageSummary(commit.message, ELISION)
            hashText = commit.oid.hex[:settings.prefs.shortHashChars]
            authorText = abbreviatePerson(commit.author, settings.prefs.authorDisplayStyle)

            qdt = QDateTime.fromSecsSinceEpoch(commit.author.time)
            dateText = option.locale.toString(qdt, settings.prefs.shortTimeFormat)
            if self.state.activeCommitOid == commit.oid:
                painter.setFont(self.activeCommitFont)

            searchBar: SearchBar = self.parent().searchBar
            searchTerm: str = searchBar.searchTerm
            searchTermLooksLikeHash: bool = searchBar.searchTermLooksLikeHash
        else:
            oid = UC_FAKEID
            commit = None

            prefix = ""
            numUncommittedChanges = self.state.numUncommittedChanges
            if numUncommittedChanges > 0:
                prefix = f"({numUncommittedChanges}) "

            hashText = "·" * settings.prefs.shortHashChars
            authorText = ""
            dateText = ""
            painter.setFont(self.uncommittedFont)

            summaryText = prefix + self.tr("Uncommitted Changes")
            draftCommitMessage = self.state.getDraftCommitMessage()
            if draftCommitMessage:
                draftLine = messageSummary(draftCommitMessage)[0]
                summaryText += f": “{messageSummary(draftCommitMessage)[0].strip()}”"

            searchTerm = ""
            searchTermLooksLikeHash = False

        # Get metrics now so the message gets elided according to the custom font style
        # that may have been just set for this commit.
        metrics: QFontMetrics = painter.fontMetrics()

        def elide(text):
            return metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())

        def highlight(x1: int, x2: int):
            if isSelected:
                painter.drawRect(rect.left() + x1, rect.top() + 1, x2 - x1, rect.height() - 2)
            else:
                painter.fillRect(rect.left() + x1, rect.top(), x2 - x1, rect.height(), colors.yellow)

        # ------ Highlight searched hash
        if searchTerm and searchTermLooksLikeHash and commit and commit.hex.startswith(searchTerm):
            x1 = 0
            x2 = min(len(hashText), len(searchTerm)) * hcw
            highlight(x1, x2)

        # ------ Hash
        charRect = QRect(leftBoundHash, rect.top(), hcw, rect.height())
        painter.save()
        if not isSelected:  # use muted color for hash if not selected
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.PlaceholderText))
        for hashChar in hashText:
            painter.drawText(charRect, Qt.AlignmentFlag.AlignCenter, hashChar)
            charRect.translate(hcw, 0)
        painter.restore()

        # ------ Graph
        rect.setLeft(leftBoundSummary)
        # if commit is not None:
        paintGraphFrame(self.state, oid, painter, rect, outlineColor)

        # ------ Callouts
        if oid in self.state.reverseRefCache:
            homeBranch = RefPrefix.HEADS + self.state.homeBranch

            painter.save()
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

                if refName == homeBranch:
                    calloutFont = self.activeCalloutFont
                    calloutFontMetrics = self.activeCalloutFontMetrics
                    calloutText = ACTIVE_BULLET + calloutText
                else:
                    calloutFont = self.calloutFont
                    calloutFontMetrics = self.calloutFontMetrics

                painter.setFont(calloutFont)
                painter.setPen(calloutColor)
                rect.setLeft(rect.right())
                label = F"[{calloutText}] "
                rect.setWidth(int(calloutFontMetrics.horizontalAdvance(label)))  # must be int for pyqt5 compat!
                painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, label)
            painter.restore()

        # ------ Message
        # use muted color for foreign commit messages if not selected
        if not isSelected and commit and commit.oid in self.state.foreignCommits:
            painter.setPen(Qt.GlobalColor.gray)
        rect.setLeft(rect.right())
        rect.setRight(leftBoundName - XMARGIN)

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
            highlight(x1, x2)

        elidedSummaryText = elide(summaryText)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elidedSummaryText)

        # ------ Author
        rect.setLeft(leftBoundName)
        rect.setRight(leftBoundDate - XMARGIN)

        # Highlight searched author
        if searchTerm and commit:
            needleIndex = authorText.lower().find(searchTerm)
            if needleIndex >= 0:
                x1 = metrics.horizontalAdvance(authorText, needleIndex)
                x2 = metrics.horizontalAdvance(authorText, needleIndex + len(searchTerm))
                highlight(x1, x2)

        # Draw author name
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, elide(authorText) + "  ")

        # ------ Date
        rect.setLeft(leftBoundDate)
        rect.setRight(rightBound)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(dateText))

        # ----------------
        painter.restore()

        # Tooltip metrics
        summaryIsElided = len(elidedSummaryText) == 0 or elidedSummaryText.endswith(("…", ELISION))
        model = index.model()
        model.setData(index, summaryIsElided, CommitLogModel.MessageElidedRole)
        model.setData(index, leftBoundName, CommitLogModel.AuthorColumnXRole)

    def _paintError(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex, exc: BaseException):
        """Last-resort row drawing routine used if _paint raises an exception."""

        text = "?" * 7
        with contextlib.suppress(BaseException):
            commit: Commit = index.data(CommitLogModel.CommitRole)
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
