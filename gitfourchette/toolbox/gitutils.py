from gitfourchette import porcelain
from gitfourchette.trtables import translateNameValidationCode
from gitfourchette.qt import translate
import enum
import pygit2
import os
import re
import stat


INITIALS_PATTERN = re.compile(r"(?:^|\s|-)+([^\s\-])[^\s\-]*")


class AuthorDisplayStyle(enum.IntEnum):
    FULL_NAME = 1
    FIRST_NAME = 2
    LAST_NAME = 3
    INITIALS = 4
    FULL_EMAIL = 5
    ABBREVIATED_EMAIL = 6


def abbreviatePerson(sig: pygit2.Signature, style: AuthorDisplayStyle = AuthorDisplayStyle.FULL_NAME):
    if style == AuthorDisplayStyle.FULL_NAME:
        return sig.name

    elif style == AuthorDisplayStyle.FIRST_NAME:
        return sig.name.split(' ')[0]

    elif style == AuthorDisplayStyle.LAST_NAME:
        return sig.name.split(' ')[-1]

    elif style == AuthorDisplayStyle.INITIALS:
        return re.sub(INITIALS_PATTERN, r"\1", sig.name)

    elif style == AuthorDisplayStyle.FULL_EMAIL:
        return sig.email

    elif style == AuthorDisplayStyle.ABBREVIATED_EMAIL:
        emailParts = sig.email.split('@', 1)
        if len(emailParts) == 2 and emailParts[1] == "users.noreply.github.com":
            # Strip ID from GitHub noreply addresses (1234567+username@users.noreply.github.com)
            return emailParts[0].split('+', 1)[-1]
        else:
            return emailParts[0]

    else:
        return sig.email


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


def simplifyOctalFileMode(m: int):
    if m in [pygit2.GIT_FILEMODE_BLOB, pygit2.GIT_FILEMODE_BLOB_EXECUTABLE]:
        m &= ~0o100000
    return m


def translateDeltaStatus(statusChar: str):
    # see git_diff_status_char (diff_print.c)
    statusCaptions = {
        "A": translate("git", "added"),
        "C": translate("git", "copied"),
        "D": translate("git", "deleted"),
        "I": translate("git", "ignored"),
        "M": translate("git", "modified"),
        "R": translate("git", "renamed"),
        "T": translate("git", "file type changed"),
        "U": translate("git", "updated but unmerged"),
        "X": translate("git", "unreadable"),
        "?": translate("git", "untracked"),
        "!": translate("git", "merge conflict"),  # this char is made up within GitFourchette
    }
    return statusCaptions.get(statusChar, f"unknown status {statusChar}")


def translateFileMode(m: int):
    fileModeTable = {
        0                                  : translate("git", "deleted", "unreadable/deleted file mode 0o000000"),
        pygit2.GIT_FILEMODE_BLOB           : translate("git", "normal", "default file mode 0o100644"),
        pygit2.GIT_FILEMODE_BLOB_EXECUTABLE: translate("git", "executable", "executable file mode 0o100755"),
        pygit2.GIT_FILEMODE_LINK           : translate("git", "link", "as in 'symlink' - file mode 0o120000"),
        pygit2.GIT_FILEMODE_TREE           : translate("git", "tree", "as in 'directory tree' - file mode 0o40000"),
        pygit2.GIT_FILEMODE_COMMIT         : translate("git", "commit", "'commit' file mode 0o160000"),
    }
    return fileModeTable.get(m, f"{m:o}")
