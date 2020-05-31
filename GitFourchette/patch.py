import git
import tempfile
import copy
import os
from typing import List, Generator


class LineData:
    cursorStart: int  # position of the cursor at the start of the line in the DiffView widget
    lineA: int  # line number in file 'A'
    lineB: int  # line number in file 'B'
    diffLineIndex: int  # index of the diff line in the unified diff itself
    data: str


def extraContext(lineDataIter, contextLines: int) -> Generator[LineData, None, None]:
    """
    Generates a finite amount of 'context' LineDatas from
    the LineData iterator given as input.
    """
    ld: LineData
    for ld in lineDataIter:
        diffChar = ld.data[0]
        if diffChar == '@':
            # Hunk separator. It's useless to keep looking for context in this direction.
            break
        elif diffChar == '-' or diffChar == ' ':
            # If it's a '-', it's a line that was in A, and it got removed in B.
            # But the change is not part of the patch. So treat it as context.
            contextLD = copy.copy(ld)
            contextLD.data = ' ' + ld.data[1:]  # doctor the line to be context
            yield contextLD
            contextLines -= 1
            if contextLines <= 0:  # stop if we have enough context
                return
        elif diffChar == '+':
            # Line that wasn't in A.
            # But the change is not part of the patch, so just ignore it.
            pass  # ignore
        else:
            raise Exception("Unknown diffChar")


def makePatch(a_path: str, b_path: str, lineData: List[LineData], ldStart: int, ldEnd: int, contextLines: int = 3) -> str:
    """
    Creates a patch (in unified diff format) from the range of selected diff lines given as input.
    """

    # Get the LineData objects within the range,
    # create barebones hunks (lists of contiguous LineData)
    hunks = []
    hunkLines = None
    for i in range(ldStart, ldEnd):
        ld = lineData[i]
        if ld.data[0] == '@':
            hunkLines = None
        else:
            if not hunkLines:
                hunkLines = []
                hunks.append(hunkLines)
            hunkLines.append(ld)

    if len(hunks) == 0:
        print("patch is empty")
        return

    firstDiffLine = hunks[0][0].diffLineIndex
    lastDiffLine = hunks[-1][-1].diffLineIndex

    # Extend first hunk with context upwards
    for contextLine in extraContext(reversed(lineData[:firstDiffLine]), contextLines):
        hunks[0].insert(0, contextLine)

    # Extend last hunk with context downwards
    for contextLine in extraContext(lineData[lastDiffLine + 1:], contextLines):
        hunks[-1].append(contextLine)

    # Assemble patch text
    patch = ""
    patch += F"--- a/{a_path}\n"
    patch += F"+++ b/{b_path}\n"
    for hunkLines in hunks:
        hunkPatch = ""
        hunkStartA = hunkLines[0].lineA
        hunkStartB = hunkLines[0].lineB
        hunkLenA = 0
        hunkLenB = 0
        for line in hunkLines:
            assert line.data[0] in ' +-'
            hunkPatch += line.data
            hunkLenA += 0 if line.data[0] == '+' else 1
            hunkLenB += 0 if line.data[0] == '-' else 1
        patch += F"@@ -{hunkStartA},{hunkLenA} +{hunkStartB},{hunkLenB} @@\n"
        patch += hunkPatch

    # This is required for git to accept staging hunks without newlines at the end.
    if not patch.endswith('\n'):
        patch += "\n\\ No newline at end of file"

    return patch


def applyPatch(repo: git.Repo, patchData: str, reverse: bool) -> str:
    prefix = F"gitfourchette-{os.path.basename(repo.working_tree_dir)}-"
    with tempfile.NamedTemporaryFile(mode='wb', suffix=".patch", prefix=prefix, delete=False) as patchFile:
        print(F"_____________ {patchFile.name} ______________\n{patchData}\n________________")
        patchFile.write(bytes(patchData, 'utf-8'))
        patchFile.flush()
        return repo.git.apply(patchFile.name, cached=True, reverse=reverse)


