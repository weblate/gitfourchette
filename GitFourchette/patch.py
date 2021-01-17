import git
import tempfile
import copy
import os
import difflib
from typing import Generator, Iterator


class LineData:
    cursorStart: int  # position of the cursor at the start of the line in the DiffView widget
    lineA: int  # line number in file 'A'
    lineB: int  # line number in file 'B'
    diffLineIndex: int  # index of the diff line in the unified diff itself
    data: bytes


# Error raised by makePatchFromGitDiff when the diffed file appears to be binary.
class LooksLikeBinaryError(Exception):
    pass


def makePatchFromGitDiff(
        repo: git.Repo,
        change: git.Diff,
        allowRawFileAccess: bool = False,
        allowBinaryPatch: bool = False,
) -> Iterator[bytes]:
    # added files (that didn't exist before) don't have an a_blob
    if change.a_blob:
        a = change.a_blob.data_stream.read()
    else:
        a = b""

    # Deleted file: no b_blob
    if change.change_type == "D":
        assert not change.b_blob
        b = b""
    elif change.b_blob:
        b = change.b_blob.data_stream.read()
    elif allowRawFileAccess:
        # If there is no b-blob and it's not a D-change,
        # then it's probably an M-change that isn't committed yet.
        with open(os.path.join(repo.working_tree_dir, change.b_path), 'rb') as f:
            b = f.read()
    else:
        b = b""

    if (not allowBinaryPatch) and ((b'\x00' in a) or (b'\x00' in b)):
        raise LooksLikeBinaryError()

    return difflib.diff_bytes(
        difflib.unified_diff,
        a.splitlines(keepends=True),
        b.splitlines(keepends=True),
        fromfile=change.a_rawpath,
        tofile=change.b_rawpath
    )


def extraContext(
        lineDataIter: Iterator[LineData],
        contextLines: int,
        plusLinesAreContext: bool
) -> Generator[LineData, None, None]:
    """
    Generates a finite amount of 'context' LineDatas from
    the LineData iterator given as input.
    """

    if not plusLinesAreContext:
        # A is our reference version. We ignore any differences with B.
        # '-' is a line that exists in A (not in B). Treat line as context.
        # '+' is a line that isn't in A (only in B). Ignore line.
        contextPrefix, ignorePrefix = b'-', b'+'
    else:
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
        plusLinesAreContext: bool,
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

    # Extend first hunk with context upwards
    for contextLine in extraContext(reversed(lineData[:firstDiffLine]), contextLines, plusLinesAreContext):
        hunks[0].insert(0, contextLine)

    # Extend last hunk with context downwards
    for contextLine in extraContext(lineData[lastDiffLine + 1:], contextLines, plusLinesAreContext):
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


def applyPatch(repo: git.Repo, patchData: bytes, cached: bool = True, reverse: bool = False) -> str:
    prefix = F"gitfourchette-{os.path.basename(repo.working_tree_dir)}-"
    with tempfile.NamedTemporaryFile(mode='wb', suffix=".patch", prefix=prefix, delete=False) as patchFile:
        #print(F"_____________ {patchFile.name} ______________\n{patchData.decode('utf-8', errors='replace')}\n________________")
        patchFile.write(patchData)
        patchFile.flush()
        return repo.git.apply(patchFile.name, cached=cached, reverse=reverse)
