from dataclasses import dataclass

from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.diffview.specialdiff import SpecialDiffError
from gitfourchette.nav import NavLocator, NavFlags
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.subpatch import DiffLinePos

MAX_LINE_LENGTH = 10_000


@dataclass
class LineData:
    text: str
    "Line text for visual representation."

    hunkPos: DiffLinePos
    "Which hunk this line pertains to, and its position in the hunk."

    diffLine: DiffLine | None = None
    "pygit2 diff line data."

    cursorStart: int = -1
    "Cursor position at start of line in QDocument."

    cursorEnd: int = -1
    "Cursor position at end of line in QDocument."

    clumpID: int = -1
    "Which clump this line pertains to. 'Clumps' are groups of adjacent +/- lines."


class DiffStyle:
    def __init__(self):
        if settings.prefs.diff_colorblindFriendlyColors:
            self.minusColor = QColor(colors.orange)
            self.plusColor = QColor(colors.teal)
        else:
            self.minusColor = QColor(0xff5555)   # Lower-saturation alternative for e.g. foreground text: 0x993333
            self.plusColor = QColor(0x55ff55)   # Lower-saturation alternative for e.g. foreground text: 0x339933

        self.minusColor.setAlpha(0x58)
        self.plusColor.setAlpha(0x58)

        self.plusBF = QTextBlockFormat()
        self.plusBF.setBackground(self.plusColor)

        self.minusBF = QTextBlockFormat()
        self.minusBF.setBackground(self.minusColor)

        self.arobaseBF = QTextBlockFormat()
        self.arobaseCF = QTextCharFormat()
        self.arobaseCF.setFontItalic(True)
        self.arobaseCF.setForeground(QColor(0, 80, 240))

        self.warningCF1 = QTextCharFormat()
        self.warningCF1.setFontWeight(QFont.Weight.Bold)
        self.warningCF1.setForeground(QColor(200, 30, 0))


@dataclass
class DiffDocument:
    document: QTextDocument
    lineData: list[LineData]
    style: DiffStyle

    @staticmethod
    def fromPatch(patch: Patch, locator: NavLocator):
        if patch.delta.similarity == 100:
            raise SpecialDiffError.noChange(patch.delta)

        # Don't show contents if file appears to be binary.
        if patch.delta.is_binary:
            raise SpecialDiffError.binaryDiff(patch.delta)

        # Don't load large diffs.
        threshold = settings.prefs.diff_largeFileThresholdKB * 1024
        if len(patch.data) > threshold and not locator.hasFlags(NavFlags.AllowLargeDiffs):
            locale = QLocale()
            humanSize = locale.formattedDataSize(len(patch.data))
            target = locator.withExtraFlags(NavFlags.AllowLargeDiffs)
            raise SpecialDiffError(
                translate("Diff", "This patch is too large to be previewed ({0}).").format(humanSize),
                target.toHtml(translate("Diff", "[Load diff anyway] (this may take a moment)")),
                QStyle.StandardPixmap.SP_MessageBoxWarning)

        if len(patch.hunks) == 0:
            raise SpecialDiffError.noChange(patch.delta)

        lineData = []

        clumpID = 0
        numLinesInClump = 0

        # For each line of the diff, create a LineData object.
        for hunkID, hunk in enumerate(patch.hunks):
            oldLine = hunk.old_start
            newLine = hunk.new_start

            hunkHeaderLD = LineData(text=hunk.header, hunkPos=DiffLinePos(hunkID, -1))
            lineData.append(hunkHeaderLD)

            for hunkLineNum, diffLine in enumerate(hunk.lines):
                origin = diffLine.origin
                content = diffLine.content

                # Any lines that aren't +/- break up the current clump
                if origin not in "+-" and numLinesInClump != 0:
                    clumpID += 1
                    numLinesInClump = 0

                # Skip GIT_DIFF_LINE_CONTEXT_EOFNL, GIT_DIFF_LINE_ADD_EOFNL, GIT_DIFF_LINE_DEL_EOFNL
                if origin in "=><":
                    continue

                if len(content) > MAX_LINE_LENGTH and not locator.hasFlags(NavFlags.AllowLongLines):
                    target = locator.withExtraFlags(NavFlags.AllowLongLines)
                    raise SpecialDiffError(
                        translate("Diff", "This file contains very long lines."),
                        target.toHtml(translate("Diff", "[Load diff anyway] (this may take a moment)")),
                        QStyle.StandardPixmap.SP_MessageBoxWarning)

                ld = LineData(text=content, hunkPos=DiffLinePos(hunkID, hunkLineNum), diffLine=diffLine)

                assert origin in " -+", F"diffline origin: '{origin}'"
                if origin == '+':
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == -1
                    newLine += 1
                    ld.clumpID = clumpID
                    numLinesInClump += 1
                elif origin == '-':
                    assert diffLine.new_lineno == -1
                    assert diffLine.old_lineno == oldLine
                    oldLine += 1
                    ld.clumpID = clumpID
                    numLinesInClump += 1
                else:
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == oldLine
                    newLine += 1
                    oldLine += 1

                lineData.append(ld)

        style = DiffStyle()

        document = QTextDocument()  # recreating a document is faster than clearing the existing one
        document.setObjectName("DiffPatchDocument")
        document.setDocumentLayout(QPlainTextDocumentLayout(document))

        cursor: QTextCursor = QTextCursor(document)

        # Begin batching text insertions for performance.
        # This prevents Qt from recomputing the document's layout after every line insertion.
        cursor.beginEditBlock()

        defaultBF = cursor.blockFormat()
        defaultCF = cursor.charFormat()
        showStrayCRs = settings.prefs.diff_showStrayCRs

        assert document.isEmpty()

        # Build up document from the lineData array.
        for ld in lineData:
            # Decide block format & character format
            if ld.diffLine is None:
                bf = style.arobaseBF
                cf = style.arobaseCF
            elif ld.diffLine.origin == '+':
                bf = style.plusBF
                cf = defaultCF
            elif ld.diffLine.origin == '-':
                bf = style.minusBF
                cf = defaultCF
            else:
                bf = defaultBF
                cf = defaultCF

            # Process line ending
            trailer = ""
            if ld.text.endswith('\n'):
                trimBack = -1
            elif ld.text.endswith('\r\n'):
                trimBack = -2
                if showStrayCRs:
                    trailer = "<CRLF>"
            elif ld.text.endswith('\r'):
                trimBack = -1
                if showStrayCRs:
                    trailer = "<CR>"
            else:
                trailer = translate("Diff", "<no newline at end of file>")
                trimBack = None  # yes, None. This will cancel slicing.

            if not document.isEmpty():
                cursor.insertBlock()
                ld.cursorStart = cursor.position()
            else:
                ld.cursorStart = 0

            cursor.setBlockFormat(bf)
            cursor.setBlockCharFormat(cf)
            cursor.insertText(ld.text[:trimBack])

            if trailer:
                cursor.setCharFormat(style.warningCF1)
                cursor.insertText(trailer)

            ld.cursorEnd = cursor.position()

        # Done batching text insertions.
        cursor.endEditBlock()

        return DiffDocument(document=document, lineData=lineData, style=style)
