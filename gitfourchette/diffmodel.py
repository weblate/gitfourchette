from allgit import *
from dataclasses import dataclass
from diffformats import *
import os
import patch as patchutils


@dataclass
class DiffModel:
    document: QTextDocument
    lineData: list[patchutils.LineData]
    forceWrap: bool

    @staticmethod
    def fromFailureMessage(message, details=""):
        document = QTextDocument()
        cursor = QTextCursor(document)
        cursor.setCharFormat(warningFormat1)
        cursor.insertText(message)
        if details:
            cursor.insertBlock()
            cursor.setCharFormat(warningFormat2)
            if details.startswith("Traceback"):
                cursor.insertText('\n')
            cursor.insertText(details)
        return DiffModel(document=document, lineData=[], forceWrap=True)

    @staticmethod
    def fromUntrackedFile(repo: Repository, path: str):
        fullPath = os.path.join(repo.workdir, path)

        # Don't load large files.
        fileSize = os.path.getsize(fullPath)
        if fileSize > settings.prefs.diff_largeFileThreshold:
            return DiffModel.fromFailureMessage(F"Large file warning: {fileSize:,} bytes")

        # Load entire file contents.
        with open(fullPath, 'rb') as f:
            binaryContents = f.read()

        # Don't show contents if file appears to be binary.
        if b'\x00' in binaryContents:
            return DiffModel.fromFailureMessage("File appears to be binary.")

        # Decode file contents.
        contents = binaryContents.decode('utf-8', errors='replace')

        # Create document with proper styling.
        document = QTextDocument()  # recreating a document is faster than clearing the existing one
        cursor = QTextCursor(document)
        cursor.setBlockFormat(plusBF)  # Use style for "+" lines for the entire file.
        cursor.setBlockCharFormat(plusCF)
        cursor.insertText(contents)

        return DiffModel(document=document, lineData=[], forceWrap=False)

    @staticmethod
    def fromPatch(repo: Repository, patch: Patch, allowRawFileAccess: bool = False):
        #TODO: check large files
        # Don't load large files.
        # if change.b_blob and change.b_blob.size > settings.prefs.diff_largeFileThreshold:
        #     return DiffModel.fromFailureMessage(F"Large file warning: {change.b_blob.size:,} bytes")
        # if change.a_blob and change.a_blob.size > settings.prefs.diff_largeFileThreshold:
        #     return DiffModel.fromFailureMessage(F"Large file warning: {change.a_blob.size:,} bytes")

        # Don't show contents if file appears to be binary.
        if patch.delta.is_binary:
            return DiffModel.fromFailureMessage("File appears to be binary.")

        if patch.delta.status == pygit2.GIT_DELTA_UNTRACKED:
            return DiffModel.fromUntrackedFile(repo, patch.delta.new_file.path)

        document = QTextDocument()  # recreating a document is faster than clearing the existing one
        cursor: QTextCursor = QTextCursor(document)

        assert document.isEmpty()

        lineData = []
        hunkID = 0

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
                cursor.setCharFormat(warningFormat1)
                cursor.insertText(trailer)
                cursor.setCharFormat(cf)

        # For each line of the diff, create a LineData object.
        hunk: DiffHunk
        diffLine: DiffLine
        for hunk in patch.hunks:
            hunkID += 1

            hunkHeaderLD = patchutils.LineData(
                text=hunk.header,
                cursorStart=cursor.position(),
                diffLine=None,
                hunkID=hunkID)
            bf, cf = arobaseBF, arobaseCF
            insertLineData(hunkHeaderLD)

            for diffLine in hunk.lines:
                if diffLine.origin in "=><":  # GIT_DIFF_LINE_CONTEXT_EOFNL, GIT_DIFF_LINE_ADD_EOFNL, GIT_DIFF_LINE_DEL_EOFNL
                    continue

                ld = patchutils.LineData(
                    text=diffLine.content,
                    cursorStart=cursor.position(),
                    diffLine=diffLine,
                    hunkID=hunkID)

                bf, cf = normalBF, normalCF

                assert diffLine.origin in " -+", F"diffline origin: '{diffLine.origin}'"
                if diffLine.origin == '+':
                    bf, cf = plusBF, plusCF
                elif diffLine.origin == '-':
                    bf, cf = minusBF, minusCF

                insertLineData(ld)

        return DiffModel(document=document, lineData=lineData, forceWrap=False)
