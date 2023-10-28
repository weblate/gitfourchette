"""Non-textual diffs"""
import contextlib
import re
from dataclasses import dataclass

import pygit2
from pygit2 import submodule

from gitfourchette import settings
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import isZeroId, BLANK_OID
from gitfourchette.qt import *
from gitfourchette.toolbox import *


@dataclass
class DiffConflict:
    ancestor: pygit2.IndexEntry | None
    ours: pygit2.IndexEntry | None
    theirs: pygit2.IndexEntry | None

    @property
    def deletedByUs(self):
        return not self.ours and self.theirs

    @property
    def deletedByThem(self):
        return self.ours and not self.theirs


class DiffImagePair:
    oldImage: QImage
    newImage: QImage

    def __init__(self, repo: pygit2.Repository, delta: pygit2.DiffDelta, locator: NavLocator):
        if not isZeroId(delta.old_file.id):
            imageDataA = repo[delta.old_file.id].peel(pygit2.Blob).data
        else:
            imageDataA = b''

        if isZeroId(delta.new_file.id):
            imageDataB = b''
        elif locator.context.isDirty():
            fullPath = os.path.join(repo.workdir, delta.new_file.path)
            assert os.lstat(fullPath).st_size == delta.new_file.size, "Size mismatch in unstaged image file"
            with open(fullPath, 'rb') as file:
                imageDataB = file.read()
        else:
            imageDataB = repo[delta.new_file.id].peel(pygit2.Blob).data

        self.oldImage = QImage.fromData(imageDataA)
        self.newImage = QImage.fromData(imageDataB)


class ShouldDisplayPatchAsImageDiff(Exception):
    def __init__(self):
        super().__init__("This patch should be viewed as an image diff!")


class SpecialDiffError(Exception):
    def __init__(
            self,
            message: str,
            details: str = "",
            icon=QStyle.StandardPixmap.SP_MessageBoxInformation,
            preformatted: str = "",
            longform: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.details = details
        self.icon = icon
        self.preformatted = preformatted
        self.longform = longform

    @staticmethod
    def noChange(delta: pygit2.DiffDelta):
        message = translate("Diff", "File contents didn’t change.")
        details = []

        oldFile: pygit2.DiffFile = delta.old_file
        newFile: pygit2.DiffFile = delta.new_file

        oldFileExists = not isZeroId(oldFile.id)
        newFileExists = not isZeroId(newFile.id)

        if not newFileExists:
            message = translate("Diff", "Empty file was deleted.")

        if not oldFileExists:
            if delta.status in [pygit2.GIT_DELTA_ADDED, pygit2.GIT_DELTA_UNTRACKED]:
                message = translate("Diff", "New empty file.")
            else:
                message = translate("Diff", "File is empty.")

        if oldFile.path != newFile.path:
            intro = translate("Diff", "Renamed:")
            details.append(f"{intro} “{escape(oldFile.path)}” &rarr; “{escape(newFile.path)}”.")

        if oldFileExists and oldFile.mode != newFile.mode:
            intro = translate("Diff", "Mode change:")
            details.append(f"{intro} {translateFileMode(oldFile.mode)} &rarr; {translateFileMode(newFile.mode)}.")

        return SpecialDiffError(message, "\n".join(details))

    @staticmethod
    def binaryDiff(delta: pygit2.DiffDelta):
        locale = QLocale()
        of = delta.old_file
        nf = delta.new_file

        if isImageFormatSupported(of.path) and isImageFormatSupported(nf.path):
            largestSize = max(of.size, nf.size)
            threshold = settings.prefs.diff_imageFileThresholdKB * 1024
            if largestSize > threshold:
                humanSize = locale.formattedDataSize(largestSize)
                humanThreshold = locale.formattedDataSize(threshold)
                return SpecialDiffError(
                    translate("Diff", "This image is too large to be previewed ({0}).").format(humanSize),
                    translate("Diff", "You can change the size threshold in the Preferences (current limit: {0}).").format(
                        humanThreshold),
                    QStyle.StandardPixmap.SP_MessageBoxWarning)
            else:
                return ShouldDisplayPatchAsImageDiff()
        else:
            oldHumanSize = locale.formattedDataSize(of.size)
            newHumanSize = locale.formattedDataSize(nf.size)
            return SpecialDiffError(
                translate("Diff", "File appears to be binary."),
                f"{oldHumanSize} &rarr; {newHumanSize}")

    @staticmethod
    def submoduleDiff(repo: pygit2.Repository, submodule: pygit2.Submodule, patch: pygit2.Patch):
        def parseSubprojectCommit(match: re.Match):
            hashText = ""
            suffix = ""
            dirty = False

            if not match:
                suffix = translate("Diff", "N/A")
            else:
                hashText = match.group(1)
                if hashText.endswith("-dirty"):
                    hashText = hashText.removesuffix("-dirty")
                    suffix = translate("Diff", "(with uncommitted changes)")
                    dirty = True
                with contextlib.suppress(ValueError):
                    oid = pygit2.Oid(hex=hashText)
                    hashText = shortHash(oid)

            return hashText, suffix, dirty

        oldMatch = re.search(r"^-Subproject commit (.+)$", patch.text, re.MULTILINE)
        newMatch = re.search(r"^\+Subproject commit (.+)$", patch.text, re.MULTILINE)
        oldHash, oldSuffix, _ = parseSubprojectCommit(oldMatch)
        newHash, newSuffix, newDirty = parseSubprojectCommit(newMatch)

        shortName = os.path.basename(submodule.name)
        localPath = os.path.join(repo.workdir, submodule.path)
        linkHref = QUrl.fromLocalFile(localPath).toString()
        linkText = translate("Diff", "Open submodule “{0}”").format(shortName)

        oldText = translate("Diff", "Old commit:")
        newText = translate("Diff", "New commit:")

        text1 = translate("Diff", "Submodule “<b>{0}</b>” was updated.").format(shortName)
        text2 = f"<a href='{linkHref}'>{linkText}</a>"
        text3 = (f"<table><tr><td>{oldText} </td><td><code>{oldHash}</code> {oldSuffix}</td></tr>"
                 f"<tr><td>{newText} </td><td><code>{newHash}</code> {newSuffix}</td></tr></table>")

        if newDirty:
            warning = translate("Diff", "You won’t be able to stage this update "
                                        "as long as the submodule contains uncommitted changes.")
            text3 += f"<p>\u26a0 <strong>{warning}</strong></p>"

        return SpecialDiffError(message=text1, details=text2, longform=text3)
