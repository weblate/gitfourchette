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
    text: str

    diffLine: DiffLine

    cursorStart: int  # position of the cursor at the start of the line in the DiffView widget

    hunkID: int

    lineDataIndex: int = -1  # index of the diff line in the unified diff itself


# Error raised by makePatchFromGitDiff when the diffed file appears to be binary.
class LooksLikeBinaryError(Exception):
    pass


def extraContext(
        lineDataIter: Iterator[LineData],
        contextLines: int,
        purpose: PatchPurpose
) -> Generator[LineData, None, None]:
    """
    Generates a finite amount of 'context' LineDatas from
    the LineData iterator given as input.
    """

    # The exact context lines to pick depends on whether the patch will be used to STAGE, UNSTAGE or DISCARD:
    # - When STAGING a range of lines, treat any '+' lines outside the range as non-existant.
    # - When UNSTAGING or DISCARDING a range of lines, treat any '+' lines outside the range as context.

    if purpose == PatchPurpose.STAGE:
        # A is our reference version. We ignore any differences with B.
        # '-' is a line that exists in A (not in B). Treat line as context.
        # '+' is a line that isn't in A (only in B). Ignore line.
        contextPrefix, ignorePrefix = b'-', b'+'
    else:  # UNSTAGE or DISCARD
        # B is our reference version. We ignore any differences with A.
        # '+' is a line that exists in B (not in A). Treat line as context
        # '-' is a line that isn't in B (only in A). Ignore line.
        contextPrefix, ignorePrefix = b'+', b'-'

    for ld in lineDataIter:
        diffChar = ld.data[0:1]
        if diffChar == b'@':
            # Hunk separator. It's useless to keep looking for context in this direction.
            break
        elif diffChar == contextPrefix or diffChar == b' ':  # Context
            contextLD = copy.copy(ld)
            contextLD.data = b' ' + ld.data[1:]  # doctor the line to be context
            yield contextLD
            contextLines -= 1
            if contextLines <= 0:  # stop if we have enough context
                return
        elif diffChar == ignorePrefix:  # Ignore
            pass  # ignore
        else:
            raise Exception("Unknown diffChar")


def makePatchFromLines(
        a_path: str,
        b_path: str,
        lineData: list[LineData],
        ldStart: int,
        ldEnd: int,
        purpose: PatchPurpose,
        contextLines: int = 3
) -> bytes:
    """
    Creates a patch (in unified diff format) from the range of selected diff lines given as input.
    """

    # Get the LineData objects within the range,
    # create barebones hunks (lists of contiguous LineData)
    hunks = []
    hunkLines = None
    for i in range(ldStart, ldEnd):
        ld = lineData[i]
        if ld.data[0:1] == b'@':
            hunkLines = None
        else:
            if not hunkLines:
                hunkLines = []
                hunks.append(hunkLines)
            hunkLines.append(ld)

    if len(hunks) == 0:
        print("patch is empty")
        return None

    firstDiffLine = hunks[0][0].diffLineIndex
    lastDiffLine = hunks[-1][-1].diffLineIndex

    # We have to add some context lines around the range of patched lines for git to accept the patch.

    # Extend first hunk with context upwards
    for contextLine in extraContext(reversed(lineData[:firstDiffLine]), contextLines, purpose):
        hunks[0].insert(0, contextLine)

    # Extend last hunk with context downwards
    for contextLine in extraContext(lineData[lastDiffLine + 1:], contextLines, purpose):
        hunks[-1].append(contextLine)

    # Assemble patch text
    allLinesWereContext = True
    patch = F"--- a/{a_path}\n+++ b/{b_path}\n".encode()
    for hunkLines in hunks:
        hunkPatch = b""
        hunkStartA = hunkLines[0].lineA
        hunkStartB = hunkLines[0].lineB
        hunkLenA = 0
        hunkLenB = 0
        for line in hunkLines:
            initial = line.data[0:1]
            assert initial in b' +-', "unrecognized initial character in patch line"
            hunkPatch += line.data
            hunkLenA += 0 if initial == b'+' else 1
            hunkLenB += 0 if initial == b'-' else 1
            if initial != b' ':
                allLinesWereContext = False
        patch += F"@@ -{hunkStartA},{hunkLenA} +{hunkStartB},{hunkLenB} @@\n".encode()
        patch += hunkPatch

    # This is required for git to accept staging hunks without newlines at the end.
    if not patch.endswith(b'\n'):
        patch += b"\n\\ No newline at end of file"

    if allLinesWereContext:
        print("all lines were context!")
        return None

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
