from allgit import *
from dataclasses import dataclass
from typing import Generator, Iterator
import copy
import enum
import os
import tempfile


@enum.unique
class PatchPurpose(enum.IntEnum):
    STAGE = enum.auto()
    UNSTAGE = enum.auto()
    DISCARD = enum.auto()


@dataclass
class LineData:
    # For visual representation
    text: str

    diffLine: DiffLine

    cursorStart: int  # position of the cursor at the start of the line in the DiffView widget

    hunkID: int


# Error raised by makePatchFromGitDiff when the diffed file appears to be binary.
class LooksLikeBinaryError(Exception):
    pass


def extraContext(
        lineDataIter: Iterator[LineData],
        contextLines: int,
        purpose: PatchPurpose
) -> Generator[DiffLine, None, None]:
    """
    Generates a finite amount of DiffLine objects to use as context
    from the LineData iterator given as input.
    """

    # The exact context lines to pick depends on whether the patch will be used to STAGE, UNSTAGE or DISCARD:
    # - When STAGING a range of lines, treat any '+' lines outside the range as non-existant.
    # - When UNSTAGING or DISCARDING a range of lines, treat any '+' lines outside the range as context.

    if purpose == PatchPurpose.STAGE:
        # A is our reference version. We ignore any differences with B.
        # '-' is a line that exists in A (not in B). Treat line as context.
        # '+' is a line that isn't in A (only in B). Ignore line.
        contextPrefix, ignorePrefix = '-', '+'
    else:  # UNSTAGE or DISCARD
        # B is our reference version. We ignore any differences with A.
        # '+' is a line that exists in B (not in A). Treat line as context
        # '-' is a line that isn't in B (only in A). Ignore line.
        contextPrefix, ignorePrefix = '+', '-'

    for lineData in lineDataIter:
        if not lineData.diffLine:
            # Hunk separator. It's useless to keep looking for context in this direction.
            break
        diffChar = lineData.diffLine.origin
        if diffChar == contextPrefix or diffChar == ' ':  # Context
            yield lineData.diffLine
            contextLines -= 1
            if contextLines <= 0:  # stop if we have enough context
                return
        elif diffChar == ignorePrefix:  # Ignore
            pass  # ignore
        else:
            raise Exception("Unknown diffChar")


def makePatchFromLines(
        oldPath: str,
        newPath: str,
        lineData: list[LineData],
        selectionStartIndex: int,  # index of first selected line in LineData list
        selectionEndIndex: int,  # index of last selected line in LineData list
        purpose: PatchPurpose,
        contextLines: int = 3
) -> bytes:
    """
    Creates a patch (in unified diff format) from the range of selected diff lines given as input.
    """

    @dataclass
    class HunkLine:
        diffLine: DiffLine
        originOverride: str

    # Get the LineData objects within the range,
    # create barebones hunks (lists of contiguous LineData)
    hunks: list[list[HunkLine]] = []
    firstIndex = -1
    lastIndex = -1

    for i in range(selectionStartIndex, selectionEndIndex):
        ld = lineData[i]
        if not ld.diffLine:  # hunk separator
            hunks.append([])  # begin new hunk
        else:
            if len(hunks) == 0:
                hunks.append([])
            hunks[-1].append(HunkLine(ld.diffLine, ld.diffLine.origin))
            if firstIndex < 0:
                firstIndex = i
            lastIndex = i

    if firstIndex < 0:  # patch is empty
        return b""  # don't bother

    # We have to add some context lines around the range of patched lines for git to accept the patch.

    # Extend first hunk with context upwards
    for contextLine in extraContext(reversed(lineData[:firstIndex]), contextLines, purpose):
        hunks[0].insert(0, HunkLine(contextLine, ' '))

    # Extend last hunk with context downwards
    for contextLine in extraContext(lineData[lastIndex + 1:], contextLines, purpose):
        hunks[-1].append(HunkLine(contextLine, ' '))

    # Assemble patch text
    allLinesWereContext = True
    patch = F"""\
diff --git a/{oldPath} b/{newPath}
--- a/{oldPath}
+++ b/{newPath}
""".encode()
    #patch = F"--- a/{oldPath}\n+++ b/{newPath}\n".encode()
    for hunkLines in hunks:
        if not hunkLines:
            continue
        hunkPatch = b""
        hunkStartA = hunkLines[0].diffLine.old_lineno
        hunkStartB = hunkLines[0].diffLine.new_lineno
        assert hunkStartA >= 0, "no valid line number for hunkStartA"
        assert hunkStartB >= 0, "no valid line number for hunkStartB"
        hunkLenA = 0
        hunkLenB = 0
        for hunkLine in hunkLines:
            diffChar = hunkLine.originOverride
            assert diffChar in ' +-', "unrecognized initial character in patch line"
            hunkPatch += diffChar.encode()
            hunkPatch += hunkLine.diffLine.raw_content
            hunkLenA += 0 if diffChar == '+' else 1
            hunkLenB += 0 if diffChar == '-' else 1
            if diffChar != ' ':
                allLinesWereContext = False
        patch += F"@@ -{hunkStartA},{hunkLenA} +{hunkStartB},{hunkLenB} @@\n".encode()
        patch += hunkPatch

    # This is required for git to accept staging hunks without newlines at the end.
    if not patch.endswith(b'\n'):
        patch += b"\n\\ No newline at end of file"

    if allLinesWereContext:
        return b""  # don't bother

    return patch


def applyPatch(repo: Repository, patchData: bytes, purpose: PatchPurpose) -> str:
    if purpose == PatchPurpose.DISCARD:
        reverse = True
        cached = False
    elif purpose == PatchPurpose.STAGE:
        reverse = False
        cached = True
    elif purpose == PatchPurpose.UNSTAGE:
        reverse = True
        cached = True
    else:
        raise ValueError(F"unsupported patch purpose: {purpose}")

    prefix = F"gitfourchette-{os.path.basename(repo.workdir)}-"
    with tempfile.NamedTemporaryFile(mode='wb', suffix=".patch", prefix=prefix, delete=False) as patchFile:
        #print(F"_____________ {patchFile.name} ______________\n{patchData.decode('utf-8', errors='replace')}\n________________")
        patchFile.write(patchData)
        patchFile.flush()
        return repo.git.apply(patchFile.name, cached=cached, reverse=reverse)
