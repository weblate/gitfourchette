"""Non-textual diffs"""

from dataclasses import dataclass

import pygit2

from gitfourchette import settings
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import isZeroId
from gitfourchette.qt import *
from gitfourchette.toolbox import *


@dataclass
class DiffConflict:
    ancestor: pygit2.IndexEntry | None
    ours: pygit2.IndexEntry | None
    theirs: pygit2.IndexEntry | None


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

        oldFileExists = not isZeroId(delta.old_file.id)
        newFileExists = not isZeroId(delta.new_file.id)

        if not newFileExists:
            message = translate("Diff", "Empty file was deleted.")

        if not oldFileExists:
            if delta.status in [pygit2.GIT_DELTA_ADDED, pygit2.GIT_DELTA_UNTRACKED]:
                message = translate("Diff", "New empty file.")
            else:
                message = translate("Diff", "File is empty.")

        if delta.old_file.path != delta.new_file.path:
            details.append(translate("Diff",
                                     "Renamed:") + f" “{escape(delta.old_file.path)}” &rarr; “{escape(delta.new_file.path)}”.")

        if oldFileExists and delta.old_file.mode != delta.new_file.mode:
            details.append(translate("Diff",
                                     "Mode change:") + f" “{delta.old_file.mode:06o}” &rarr; “{delta.new_file.mode:06o}”.")

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


