from gitfourchette import porcelain
from gitfourchette.trtables import translateNameValidationCode
import pygit2
import os
import stat


def shortHash(oid: pygit2.Oid) -> str:
    from gitfourchette.settings import prefs
    return oid.hex[:prefs.shortHashChars]


def dumpTempBlob(
        repo: pygit2.Repository,
        dir: str,
        entry: pygit2.DiffFile | pygit2.IndexEntry | None,
        inBrackets: str):

    # In merge conflicts, the IndexEntry may be None (for the ancestor, etc.)
    if not entry:
        return ""

    blobId = entry.id
    blob: pygit2.Blob = repo[blobId].peel(pygit2.Blob)
    name, ext = os.path.splitext(os.path.basename(entry.path))
    name = F"[{inBrackets}]{name}{ext}"
    path = os.path.join(dir, name)
    with open(path, "wb") as f:
        f.write(blob.data)

    # Make it read-only (this will probably not work on Windows)
    mode = os.stat(path).st_mode
    readOnlyMask = ~(stat.S_IWRITE | stat.S_IWGRP | stat.S_IWOTH)
    os.chmod(path, mode & readOnlyMask)

    return path


def nameValidationMessage(name: str, reservedNames: list[str], nameTakenMessage: str = "") -> str:
    try:
        porcelain.validateRefName(name, reservedNames)
    except porcelain.NameValidationError as exc:
        if exc.code == porcelain.NameValidationError.NAME_TAKEN and nameTakenMessage:
            return nameTakenMessage
        else:
            return translateNameValidationCode(exc.code)

    return ""  # validation passed, no error
