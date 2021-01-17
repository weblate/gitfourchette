import git
import re
import os
from typing import List
from dataclasses import dataclass
import patch
from util import excStrings
from diff_formats import *


# Hunk header pattern.
# Examples of matches:
# @@ -4,6 +4,7 @@
# @@ -1 +1,165 @@
# @@ -0,0 +1 @@
hunkRE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$")


@dataclass
class DiffModel:
    document: QTextDocument
    lineData: list
    forceWrap: bool


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
    return DiffModel(document, None, True)


def fromUntrackedFile(repo: git.Repo, path: str):
    fullPath = os.path.join(repo.working_tree_dir, path)

    # Don't load large files.
    fileSize = os.path.getsize(fullPath)
    if fileSize > settings.prefs.diff_largeFileThreshold:
        return fromFailureMessage(F"Large file warning: {fileSize:,} bytes")

    # Load entire file contents.
    with open(fullPath, 'rb') as f:
        binaryContents = f.read()

    # Don't show contents if file appears to be binary.
    if b'\x00' in binaryContents:
        return fromFailureMessage("File appears to be binary.")

    # Decode file contents.
    contents = binaryContents.decode('utf-8', errors='replace')

    # Create document with proper styling.
    document = QTextDocument()  # recreating a document is faster than clearing the existing one
    cursor = QTextCursor(document)
    cursor.setBlockFormat(plusBF)  # Use style for "+" lines for the entire file.
    cursor.setBlockCharFormat(plusCF)
    cursor.insertText(contents)

    return DiffModel(document, None, False)


def fromGitDiff(repo: git.Repo, change: git.Diff, allowRawFileAccess: bool = False):
    # Don't load large files.
    if change.b_blob and change.b_blob.size > settings.prefs.diff_largeFileThreshold:
        return fromFailureMessage(F"Large file warning: {change.b_blob.size:,} bytes")
    if change.a_blob and change.a_blob.size > settings.prefs.diff_largeFileThreshold:
        return fromFailureMessage(F"Large file warning: {change.a_blob.size:,} bytes")

    # Create binary diff.
    try:
        binaryPatchGenerator = patch.makePatchFromGitDiff(repo, change, allowRawFileAccess)
    except patch.LooksLikeBinaryError:
        # Don't show contents if file appears to be binary.
        return fromFailureMessage("File appears to be binary.")

    document = QTextDocument()  # recreating a document is faster than clearing the existing one
    cursor: QTextCursor = QTextCursor(document)

    firstBlock = True
    lineData = []
    lineA = -1
    lineB = -1

    # For each line of the diff, create a LineData object.
    for rawLine in binaryPatchGenerator:
        # skip diff header
        if rawLine.startswith(b"+++ ") or rawLine.startswith(b"--- "):
            continue

        textLine = rawLine.decode('utf-8', errors='replace')

        ld = patch.LineData()
        ld.cursorStart = cursor.position()
        ld.lineA = lineA
        ld.lineB = lineB
        ld.diffLineIndex = len(lineData)
        ld.data = rawLine
        lineData.append(ld)

        bf, cf = normalBF, normalCF
        trimFront, trimBack = 1, None
        trailer = None

        if rawLine.startswith(b'@@'):
            bf, cf = arobaseBF, arobaseCF
            trimFront = 0
            hunkMatch = hunkRE.match(textLine)
            lineA = int(hunkMatch.group(1))
            lineB = int(hunkMatch.group(3))
        elif rawLine.startswith(b'+'):
            bf, cf = plusBF, plusCF
            lineB += 1
        elif rawLine.startswith(b'-'):
            bf, cf = minusBF, minusCF
            lineA += 1
        else:
            # context line
            lineA += 1
            lineB += 1

        if rawLine.endswith(b'\r\n'):
            trimBack = -2
            if settings.prefs.diff_showStrayCRs:
                trailer = "<CR>"
        elif rawLine.endswith(b'\n'):
            trimBack = -1
        else:
            trailer = "<no newline at end of file>"

        if not firstBlock:
            cursor.insertBlock()
            ld.cursorStart = cursor.position()
        firstBlock = False

        cursor.setBlockFormat(bf)
        cursor.setCharFormat(cf)
        cursor.insertText(textLine[trimFront:trimBack])

        if trailer:
            cursor.setCharFormat(warningFormat1)
            cursor.insertText(trailer)
            cursor.setCharFormat(cf)

    return DiffModel(document, lineData, False)
