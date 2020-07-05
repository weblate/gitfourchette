from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
from datetime import datetime
import settings
import colors
from RepoState import CommitMetadata, RepoState
from util import sign, messageSummary


LANE_WIDTH = 10
LANE_THICKNESS = 2
DOT_RADIUS = 3


def getColor(i):
    return colors.rainbowBright[i % len(colors.rainbowBright)]


# Draw lane lines.
def drawLanes(meta: CommitMetadata, painter: QPainter, rect: QRect):
    painter.save()
    painter.setRenderHints(QPainter.Antialiasing, True)

    # Ensure all coordinates below are integers so our straight lines don't look blurry
    x = int(rect.left() + LANE_WIDTH // 2)
    top = int(rect.y())
    bottom = int(rect.y() + rect.height())  # Don't use rect.bottom(), which for historical reasons doesn't return what we want (see Qt docs)
    middle = (top + bottom) // 2

    MAX_LANES = settings.prefs.graph_maxLanes

    # If there are too many lanes, cut off to MAX_LANES so the view stays somewhat readable.
    lanesAbove = meta.laneFrame.lanesAbove[:MAX_LANES]
    lanesBelow = meta.laneFrame.lanesBelow[:MAX_LANES]
    MY_LANE = meta.laneFrame.myLane
    TOTAL = max(len(lanesAbove), len(lanesBelow))

    remapAbove = []
    remapBelow = []
    if settings.prefs.graph_flattenLanes:
        ai, bi = -1, -1
        for i in range(TOTAL):
            if i < len(lanesAbove) and lanesAbove[i]: ai += 1
            if i < len(lanesBelow) and lanesBelow[i]: bi += 1
            remapAbove.append(ai)
            remapBelow.append(bi)
        FLAT_TOTAL = max(ai, bi)
    else:
        remap = list(range(TOTAL))
        remapAbove = remap
        remapBelow = remap
        FLAT_TOTAL = TOTAL

    rect.setRight(x + FLAT_TOTAL * LANE_WIDTH)

    # find out position of my lane
    myRemap = -1
    if MY_LANE < len(remapBelow):
        myRemap = remapBelow[MY_LANE]
    if myRemap < 0 and MY_LANE < len(remapAbove):
        myRemap = remapAbove[MY_LANE]
    mx = x + myRemap * LANE_WIDTH

    # parent info for Fork Down
    parentsRemaining = set(meta.parentHashes)
    parent0 = meta.parentHashes[0] if len(meta.parentHashes) > 0 else None

    path = QPainterPath()

    # draw lines
    # TODO: range(TOTAL-1,-1,-1) makes junctions more readable,
    # TODO: but we should draw "straight" lines (unaffected by the
    # TODO: commit) underneath junction lines
    for i in range(TOTAL):
        commitAbove = lanesAbove[i] if i < len(lanesAbove) else None
        commitBelow = lanesBelow[i] if i < len(lanesBelow) else None
        ax = x + remapAbove[i] * LANE_WIDTH
        bx = x + remapBelow[i] * LANE_WIDTH

        # position of lane `i` relative to MY_LANE: can be -1 (left), 0 (same), or +1 (right)
        direction = sign(i - MY_LANE)

        # Straight
        if commitAbove and commitAbove == commitBelow:
            path.moveTo(ax, top)
            path.cubicTo(ax,middle, bx,middle, bx,bottom)

        # Fork Up
        if commitAbove == meta.hexsha:
            path.moveTo(mx, middle)
            path.lineTo(ax-direction*LANE_WIDTH, middle)
            path.quadTo(ax,middle, ax,top)

        # Fork Down
        if commitBelow in parentsRemaining and (commitBelow != parent0 or i == MY_LANE):
            path.moveTo(mx, middle)
            path.lineTo(bx-direction*LANE_WIDTH, middle)
            path.quadTo(bx,middle, bx,bottom)
            parentsRemaining.remove(commitBelow)

        if not path.isEmpty():
            # white outline
            painter.setPen(QPen(Qt.white, LANE_THICKNESS + 2, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            # actual color
            painter.setPen(QPen(getColor(i), LANE_THICKNESS, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            path.clear()

    # show warning if we have too many lanes
    if len(meta.laneFrame.lanesBelow) > MAX_LANES:
        extraText = F"+{len(meta.laneFrame.lanesBelow) - MAX_LANES} lanes >>>  "
        painter.drawText(rect, Qt.AlignRight, extraText)

    # draw bullet point for this commit if it's within the lanes that are shown
    if MY_LANE < MAX_LANES:
        c = getColor(MY_LANE)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(c)
        painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    painter.restore()

    # add some padding to the right
    rect.setRight(rect.right() + LANE_WIDTH)


# différence entre QItemDelegate et QStyledItemDelegate?
class GraphDelegate(QItemDelegate):
    def __init__(self, repoWidget, parent=None):
        super().__init__(parent)
        self.repoWidget = repoWidget

    @property
    def state(self) -> RepoState:
        return self.repoWidget.state

    def paint(self, painter, option, index):
        # print("Render Index Row: " +  str(index.row()))
        # super(__class__, self).paint(painter, option, index)

        XMargin = 4
        ColW_Author = 16
        ColW_Hash = settings.prefs.shortHashChars + 1
        ColW_Date = 16

        painter.save()

        palette: QPalette = option.palette
        pcg = QPalette.ColorGroup.Current if option.state & QStyle.State_HasFocus else QPalette.ColorGroup.Disabled

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, palette.color(pcg, QPalette.ColorRole.Highlight))
            painter.setPen(palette.color(QPalette.ColorRole.HighlightedText))

        rect = QRect(option.rect)
        rect.setLeft(rect.left() + XMargin)
        rect.setRight(rect.right() - XMargin)

        # Get metrics of '0' before setting a custom font,
        # so that alignments are consistent in all commits regardless of bold or italic.
        zw = painter.fontMetrics().horizontalAdvance('0')

        if index.row() > 0:
            meta = index.data()

            summary, contd = messageSummary(meta.body)

            data = {
                'hash': meta.hexsha[:settings.prefs.shortHashChars],
                'author': meta.authorEmail.split('@')[0],  # [:8],
                'date': datetime.fromtimestamp(meta.authorTimestamp).strftime(settings.prefs.shortTimeFormat),
                'message': summary,
            }

            #assert meta.laneFrame, "lane frame missing from commit metadata"
            #assert meta.laneFrame.myLane >= 0, "illegal lane number"

            if meta.bold:
                painter.setFont(settings.boldFont)
        else:
            meta = None
            data = {
                'hash': "·" * settings.prefs.shortHashChars,
                'author': "",
                'date': "",
                'message': index.data(),
            }
            painter.setFont(settings.alternateFont)

        # Get metrics now so the message gets elided according to the custom font style
        # that may have been just set for this commit.
        metrics = painter.fontMetrics()

        # ------ Hash
        rect.setWidth(ColW_Hash * zw)
        charRect = QRect(rect.left(), rect.top(), zw, rect.height())
        painter.save()
        painter.setPen(palette.color(pcg, QPalette.ColorRole.PlaceholderText))
        for hashChar in data['hash']:
            painter.drawText(charRect, Qt.AlignCenter, hashChar)
            charRect.translate(zw, 0)
        painter.restore()

        # ------ Graph
        rect.setLeft(rect.right())
        if meta is not None and meta.laneFrame:
            drawLanes(meta, painter, rect)

        # ------ tags
        def drawTagOrRef(name, color):
            painter.save()
            painter.setFont(settings.smallFont)
            painter.setPen(color)
            rect.setLeft(rect.right())
            label = F"[{name}] "
            rect.setWidth(settings.smallFontMetrics.horizontalAdvance(label) + 1)
            painter.drawText(rect, Qt.AlignVCenter, label)
            painter.restore()
        if meta is not None:
            if meta.hexsha in self.state.refCache:
                for ref in self.state.refCache[meta.hexsha]:
                    drawTagOrRef(ref, Qt.darkMagenta)
            if meta.hexsha in self.state.tagCache:
                for tag in self.state.tagCache[meta.hexsha]:
                    drawTagOrRef(tag, Qt.darkYellow)

        # ------ message
        if meta and not meta.hasLocal:
            painter.setPen(QColor(Qt.gray))
        rect.setLeft(rect.right())
        rect.setRight(option.rect.right() - (ColW_Author + ColW_Date) * zw - XMargin)
        painter.drawText(rect, Qt.AlignVCenter,
                metrics.elidedText(data['message'], Qt.ElideRight, rect.width()))

        # ------ Author
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Author * zw)
        painter.drawText(rect, Qt.AlignVCenter,
                metrics.elidedText(data['author'], Qt.ElideRight, rect.width()))

        # ------ Date
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Date * zw)
        painter.drawText(rect, Qt.AlignVCenter,
                metrics.elidedText(data['date'], Qt.ElideRight, rect.width()))

        # ------ Debug (show redrawn rows from last refresh)
        if meta and meta.debugPrefix:
            rect = QRect(option.rect)
            rect.setLeft(rect.left() + XMargin + (ColW_Hash-3) * zw)
            rect.setRight(rect.left() + 2*zw)
            painter.fillRect(rect, colors.rainbow[meta.debugRefreshId % len(colors.rainbow)])
            painter.drawText(rect, "-"+meta.debugPrefix)

        # ----------------
        painter.restore()
        pass  # QStyledItemDelegate.paint(self, painter, option, index)

    def sizeHint(self, option, index):
        # return QStyledItemDelegate.sizeHint(self, option, index)
        r = QItemDelegate.sizeHint(self, option, index)
        r.setHeight(r.height() * settings.prefs.graph_lineHeight)
        return r
