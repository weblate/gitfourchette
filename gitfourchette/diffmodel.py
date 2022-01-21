from allqt import *
from dataclasses import dataclass
from diffstyle import DiffStyle
import os
import patch as patchutils
import pygit2
import settings


@dataclass
class DiffModel:
    document: QTextDocument
    lineData: list[patchutils.LineData]
    forceWrap: bool
    style: DiffStyle

    @staticmethod
    def fromMessage(message, details="", icon=QStyle.SP_MessageBoxInformation):
        style = DiffStyle()
        document = QTextDocument()

        pixmap = QApplication.style().standardIcon(icon).pixmap(48, 48)

        document.addResource(QTextDocument.ImageResource, QUrl("icon"), pixmap)

        document.setHtml(
            "<table width='100%'>"
            "<tr>"
            "<td><img src='icon'/></td>"
            "<td width=8></td>"
            F"<td width='100%'><big>{message}</big><br/>{details}</td>"
            "</tr>"
            "</table>")

        return DiffModel(document=document, lineData=[], forceWrap=True, style=style)

    @staticmethod
    def fromUntrackedFile(repo: pygit2.Repository, path: str):
        fullPath = os.path.join(repo.workdir, path)

        # Don't load large files.
        fileSize = os.path.getsize(fullPath)
        if fileSize > settings.prefs.diff_largeFileThresholdKB * 1024:
            return DiffModel.fromMessage(
                F"This file is too large to be previewed ({fileSize//1024:,} KB).",
                "You can change the size threshold in the Preferences.",
                icon=QStyle.SP_MessageBoxWarning)

        # Load entire file contents.
        with open(fullPath, 'rb') as f:
            binaryContents = f.read()

        # Don't show contents if file appears to be binary.
        if b'\x00' in binaryContents:
            return DiffModel.fromMessage("File appears to be binary.")

        # Decode file contents.
        contents = binaryContents.decode('utf-8', errors='replace')

        # Create document with proper styling.
        style = DiffStyle()
        document = QTextDocument()  # recreating a document is faster than clearing the existing one
        cursor = QTextCursor(document)
        cursor.setBlockFormat(style.plusBF)  # Use style for "+" lines for the entire file.
        cursor.setBlockCharFormat(style.plusCF)
        cursor.insertText(contents)

        return DiffModel(document=document, lineData=[], forceWrap=False, style=style)

    @staticmethod
    def fromPatch(repo: pygit2.Repository, patch: pygit2.Patch, allowRawFileAccess: bool = False):
        # Don't show contents if file appears to be binary.
        if patch.delta.is_binary:
            return DiffModel.fromMessage("File appears to be binary.")

        if patch.delta.status == pygit2.GIT_DELTA_UNTRACKED:
            return DiffModel.fromUntrackedFile(repo, patch.delta.new_file.path)

        # Don't load large diffs.
        if len(patch.data) > settings.prefs.diff_largeFileThresholdKB * 1024:
            return DiffModel.fromMessage(
                F"This patch is too large to be previewed ({len(patch.data)//1024:,} KB).",
                "You can change the size threshold in the Preferences.",
                QStyle.SP_MessageBoxWarning)

        if len(patch.hunks) == 0:
            return DiffModel.fromMessage(F"File contents did not change.")

        style = DiffStyle()
        document = QTextDocument()  # recreating a document is faster than clearing the existing one
        cursor: QTextCursor = QTextCursor(document)

        assert document.isEmpty()

        lineData = []

        def insertLineData(ld: patchutils.LineData):
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
            cursor.setCharFormat(cf)
            cursor.insertText(ld.text[:trimBack])

            if trailer:
                cursor.setCharFormat(style.warningCF1)
                cursor.insertText(trailer)
                cursor.setCharFormat(cf)

        # For each line of the diff, create a LineData object.
        hunk: pygit2.DiffHunk
        diffLine: pygit2.DiffLine
        for hunkID, hunk in enumerate(patch.hunks):
            oldLine = hunk.old_start
            newLine = hunk.new_start

            hunkHeaderLD = patchutils.LineData(
                text=hunk.header,
                cursorStart=cursor.position(),
                diffLine=None,
                hunkPos=patchutils.DiffLinePos(hunkID, -1))
            bf, cf = style.arobaseBF, style.arobaseCF
            insertLineData(hunkHeaderLD)

            for hunkLineNum, diffLine in enumerate(hunk.lines):
                if diffLine.origin in "=><":  # GIT_DIFF_LINE_CONTEXT_EOFNL, GIT_DIFF_LINE_ADD_EOFNL, GIT_DIFF_LINE_DEL_EOFNL
                    continue

                ld = patchutils.LineData(
                    text=diffLine.content,
                    cursorStart=cursor.position(),
                    diffLine=diffLine,
                    hunkPos=patchutils.DiffLinePos(hunkID, hunkLineNum))

                bf, cf = style.normalBF, style.normalCF

                assert diffLine.origin in " -+", F"diffline origin: '{diffLine.origin}'"
                if diffLine.origin == '+':
                    bf, cf = style.plusBF, style.plusCF
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == -1
                    newLine += 1
                elif diffLine.origin == '-':
                    bf, cf = style.minusBF, style.minusCF
                    assert diffLine.new_lineno == -1
                    assert diffLine.old_lineno == oldLine
                    oldLine += 1
                else:
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == oldLine
                    newLine += 1
                    oldLine += 1

                insertLineData(ld)

        return DiffModel(document=document, lineData=lineData, forceWrap=False, style=style)
