from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.stagingstate import StagingState
from gitfourchette.subpatch import DiffLinePos
from gitfourchette.qt import *
from gitfourchette.util import isZeroId, isImageFormatSupported
from dataclasses import dataclass
import html
import os
import pygit2


@dataclass
class LineData:
    # For visual representation
    text: str

    diffLine: pygit2.DiffLine | None

    cursorStart: int  # position of the cursor at the start of the line in the DiffView widget

    hunkPos: DiffLinePos


class DiffModelError(Exception):
    def __init__(
            self,
            message: str,
            details: str = "",
            icon=QStyle.StandardPixmap.SP_MessageBoxInformation,
            preformatted: str = ""
    ):
        super().__init__(message)
        self.message = message
        self.details = details
        self.icon = icon
        self.preformatted = preformatted


class ShouldDisplayPatchAsImageDiff(Exception):
    def __init__(self):
        super().__init__("This patch should be viewed as an image diff!")


class DiffImagePair:
    oldImage: QImage
    newImage: QImage

    def __init__(self, repo: pygit2.Repository, delta: pygit2.DiffDelta, stagingState: StagingState = StagingState.UNKNOWN):
        if not isZeroId(delta.old_file.id):
            imageDataA = repo[delta.old_file.id].peel(pygit2.Blob).data
        else:
            imageDataA = b''

        if isZeroId(delta.new_file.id):
            imageDataB = b''
        elif stagingState in [StagingState.UNTRACKED, StagingState.UNSTAGED]:
            fullPath = os.path.join(repo.workdir, delta.new_file.path)
            assert os.lstat(fullPath).st_size == delta.new_file.size, "Size mismatch in unstaged image file"
            with open(fullPath, 'rb') as file:
                imageDataB = file.read()
        else:
            imageDataB = repo[delta.new_file.id].peel(pygit2.Blob).data

        self.oldImage = QImage.fromData(imageDataA)
        self.newImage = QImage.fromData(imageDataB)


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


def createDocument():
    monoFont = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if settings.prefs.diff_font:
        monoFont.fromString(settings.prefs.diff_font)

    document = QTextDocument()  # recreating a document is faster than clearing the existing one
    document.setDocumentLayout(QPlainTextDocumentLayout(document))
    document.setDefaultFont(monoFont)
    return document


def noChange(delta: pygit2.DiffDelta):
    message = "File contents didn’t change."
    details = []

    oldFileExists = not isZeroId(delta.old_file.id)

    if not oldFileExists:
        message = "File is empty."

    if delta.old_file.path != delta.new_file.path:
        details.append(F"Renamed: “{html.escape(delta.old_file.path)}” &rarr; “{html.escape(delta.new_file.path)}”.")

    if oldFileExists and delta.old_file.mode != delta.new_file.mode:
        details.append(F"Mode change: “{delta.old_file.mode:06o}” &rarr; “{delta.new_file.mode:06o}”.")

    return DiffModelError(message, "\n".join(details))


@dataclass
class DiffModel:
    document: QTextDocument
    lineData: list[LineData]
    style: DiffStyle

    @staticmethod
    def fromPatch(patch: pygit2.Patch):
        if patch.delta.similarity == 100:
            raise noChange(patch.delta)

        # Don't show contents if file appears to be binary.
        if patch.delta.is_binary:
            of = patch.delta.old_file
            nf = patch.delta.new_file
            if isImageFormatSupported(of.path) and isImageFormatSupported(nf.path):
                largestSize = max(of.size, nf.size)
                threshold = settings.prefs.diff_imageFileThresholdKB * 1024
                if largestSize > threshold:
                    humanSize = QLocale().formattedDataSize(largestSize)
                    humanThreshold = QLocale().formattedDataSize(threshold)
                    raise DiffModelError(
                        F"This image is too large to be previewed ({humanSize}).",
                        F"You can change the size threshold in the Preferences (current limit: {humanThreshold}).",
                        QStyle.StandardPixmap.SP_MessageBoxWarning)
                else:
                    raise ShouldDisplayPatchAsImageDiff()
            else:
                raise DiffModelError("File appears to be binary.")

        # Don't load large diffs.
        threshold = settings.prefs.diff_largeFileThresholdKB * 1024
        if len(patch.data) > threshold:
            humanSize = QLocale().formattedDataSize(len(patch.data))
            humanThreshold = QLocale().formattedDataSize(threshold)
            raise DiffModelError(
                F"This patch is too large to be previewed ({humanSize}).",
                F"You can change the size threshold in the Preferences (current limit: {humanThreshold}).",
                QStyle.StandardPixmap.SP_MessageBoxWarning)

        if len(patch.hunks) == 0:
            raise noChange(patch.delta)

        style = DiffStyle()
        document = createDocument()  # recreating a document is faster than clearing the existing one
        cursor: QTextCursor = QTextCursor(document)

        defaultBF = cursor.blockFormat()
        defaultCF = cursor.charFormat()

        assert document.isEmpty()

        lineData = []

        def insertLineData(ld: LineData, bf, cf):
            lineData.append(ld)

            trailer = None

            if ld.text.endswith('\r\n'):
                trimBack = -2
                if settings.prefs.diff_showStrayCRs:
                    trailer = "<CRLF>"
            elif ld.text.endswith('\r'):
                trimBack = -1
                if settings.prefs.diff_showStrayCRs:
                    trailer = "<CR>"
            elif ld.text.endswith('\n'):
                trimBack = -1
            else:
                trailer = "<no newline at end of file>"
                trimBack = None

            if not document.isEmpty():
                cursor.insertBlock()
                ld.cursorStart = cursor.position()

            cursor.setBlockFormat(bf)
            cursor.setBlockCharFormat(cf)
            cursor.insertText(ld.text[:trimBack])

            if trailer:
                cursor.setCharFormat(style.warningCF1)
                cursor.insertText(trailer)

        # For each line of the diff, create a LineData object.
        for hunkID, hunk in enumerate(patch.hunks):
            oldLine = hunk.old_start
            newLine = hunk.new_start

            hunkHeaderLD = LineData(
                text=hunk.header,
                cursorStart=cursor.position(),
                diffLine=None,
                hunkPos=DiffLinePos(hunkID, -1))
            insertLineData(hunkHeaderLD, style.arobaseBF, style.arobaseCF)

            for hunkLineNum, diffLine in enumerate(hunk.lines):
                if diffLine.origin in "=><":  # GIT_DIFF_LINE_CONTEXT_EOFNL, GIT_DIFF_LINE_ADD_EOFNL, GIT_DIFF_LINE_DEL_EOFNL
                    continue

                ld = LineData(
                    text=diffLine.content,
                    cursorStart=cursor.position(),
                    diffLine=diffLine,
                    hunkPos=DiffLinePos(hunkID, hunkLineNum))

                bf = defaultBF

                assert diffLine.origin in " -+", F"diffline origin: '{diffLine.origin}'"
                if diffLine.origin == '+':
                    bf = style.plusBF
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == -1
                    newLine += 1
                elif diffLine.origin == '-':
                    bf = style.minusBF
                    assert diffLine.new_lineno == -1
                    assert diffLine.old_lineno == oldLine
                    oldLine += 1
                else:
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == oldLine
                    newLine += 1
                    oldLine += 1

                insertLineData(ld, bf, defaultCF)

        return DiffModel(document=document, lineData=lineData, style=style)
