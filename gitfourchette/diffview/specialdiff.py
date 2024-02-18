"""Non-textual diffs"""
from contextlib import suppress
import os
import re
from dataclasses import dataclass

from gitfourchette import settings
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables


class DiffImagePair:
    oldImage: QImage
    newImage: QImage

    def __init__(self, repo: Repo, delta: DiffDelta, locator: NavLocator):
        if delta.old_file.id != NULL_OID:
            imageDataA = repo.peel_blob(delta.old_file.id).data
        else:
            imageDataA = b''

        if delta.new_file.id == NULL_OID:
            imageDataB = b''
        elif locator.context.isDirty():
            fullPath = repo.in_workdir(delta.new_file.path)
            assert os.lstat(fullPath).st_size == delta.new_file.size, "Size mismatch in unstaged image file"
            with open(fullPath, 'rb') as file:
                imageDataB = file.read()
        else:
            imageDataB = repo.peel_blob(delta.new_file.id).data

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
        self.links = DocumentLinks()

    @staticmethod
    def noChange(delta: DiffDelta):
        from gitfourchette.tasks import AbsorbSubmodule

        message = translate("Diff", "File contents didn’t change.")
        details = []
        longform = []

        oldFile: DiffFile = delta.old_file
        newFile: DiffFile = delta.new_file

        oldFileExists = oldFile.id != NULL_OID
        newFileExists = newFile.id != NULL_OID

        if not newFileExists:
            message = translate("Diff", "Empty file was deleted.")

        if not oldFileExists:
            if delta.new_file.mode == FileMode.TREE:
                treePath = os.path.normpath(delta.new_file.path)
                treeName = os.path.basename(treePath)
                message = translate("Diff", "This untracked folder is the root of another Git repository.")

                # TODO: if we had the full path to the root repo, we could just make a standard file link, and we wouldn't need the "opensubfolder" authority
                prompt1 = translate("Diff", "Open {0} in new tab").format(bquo(treeName))
                openLink = makeInternalLink("opensubfolder", treePath)
                longform.append(f"<center><p><a href='{openLink}'>{prompt1}</a></p></center>")

                prompt = translate("Diff", "Absorb {0} as submodule").format(bquo(treeName))
                taskLink = AbsorbSubmodule.makeInternalLink(path=treePath)
                longform.append(f"<center><p><a href='{taskLink}'>{prompt}</a></p></center>")
            elif delta.status in [DeltaStatus.ADDED, DeltaStatus.UNTRACKED]:
                message = translate("Diff", "New empty file.")
            else:
                message = translate("Diff", "File is empty.")

        if oldFile.path != newFile.path:
            intro = translate("Diff", "Renamed:")
            details.append(f"{intro} {hquo(oldFile.path)} &rarr; {hquo(newFile.path)}.")

        if oldFileExists and oldFile.mode != newFile.mode:
            intro = translate("Diff", "Mode change:")
            details.append(f"{intro} {TrTables.fileMode(oldFile.mode)} &rarr; {TrTables.fileMode(newFile.mode)}.")

        return SpecialDiffError(message, "\n".join(details), longform="\n".join(longform))

    @staticmethod
    def binaryDiff(delta: DiffDelta):
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
    def submoduleDiff(repo: Repo, submodule: Submodule, patch: Patch, locator: NavLocator):
        from gitfourchette.tasks import DiscardSubmoduleChanges

        def parseSubprojectCommit(match: re.Match):
            dirty = False
            if not match:
                hashText = translate("Diff", "(none)", "no commit")
            else:
                hashText = match.group(1)
                if hashText.endswith("-dirty"):
                    hashText = hashText.removesuffix("-dirty")
                    dirty = True
            return hashText, dirty

        shortName = os.path.basename(submodule.name)
        localPath = repo.in_workdir(submodule.path)
        url1 = QUrl.fromLocalFile(localPath)

        oldMatch = re.search(r"^-Subproject commit (.+)$", patch.text, re.MULTILINE)
        newMatch = re.search(r"^\+Subproject commit (.+)$", patch.text, re.MULTILINE)
        oldHash, _ = parseSubprojectCommit(oldMatch)
        newHash, newDirty = parseSubprojectCommit(newMatch)

        try:
            oid = Oid(hex=oldHash)
            url2 = QUrl(url1)
            url2.setFragment(oid.hex)
            oldTarget = f"<a href='{url2.toString()}'>{shortHash(oid)}</a>"
        except ValueError:
            oldTarget = oldHash

        try:
            oid = Oid(hex=newHash)
            url3 = QUrl(url1)
            url3.setFragment(oid.hex)
            newTarget = f"<a href='{url3.toString()}'>{shortHash(oid)}</a>"
        except ValueError:
            newTarget = newHash

        text3 = []
        if oldHash != newHash:
            with RepoContext(localPath) as subRepo:
                message1 = ""
                message2 = ""
                with suppress(LookupError, ValueError, GitError):
                    message1 = subRepo[Oid(hex=oldHash)].peel(Commit).message
                    message1 = messageSummary(message1)[0]
                    message1 = elide(message1, Qt.TextElideMode.ElideRight, 25)
                    message1 = hquo(message1)
                with suppress(LookupError, ValueError, GitError):
                    message2 = subRepo[Oid(hex=newHash)].peel(Commit).message
                    message2 = messageSummary(message2)[0]
                    message2 = elide(message2, Qt.TextElideMode.ElideRight, 25)
                    message2 = hquo(message2)

            oldText = translate("Diff", "Old:")
            newText = translate("Diff", "New:")
            table = ("<table>"
                     f"<tr><td><del><b>{oldText}</b></del> </td><td><code>{oldTarget} </code> {message1}</td></tr>"
                     f"<tr><td><add><b>{newText}</b></add> </td><td><code>{newTarget} </code> {message2}</td></tr>"
                     "</table>")

            if locator.context == NavContext.UNSTAGED:
                intro = translate("Diff", "<b>HEAD</b> was moved to another commit &ndash; you can stage this update:")
            else:
                intro = translate("Diff", "<b>HEAD</b> was moved to another commit:")
            text3.append(f"<p>{intro}<p>{table}</p></p>")

        if newDirty:
            url2 = DiscardSubmoduleChanges.makeInternalLink(path=submodule.name)
            if oldHash != newHash:
                lead = translate("Diff", "In addition, there are <b>uncommitted changes</b> in the submodule.")
            else:
                lead = translate("Diff", "There are <b>uncommitted changes</b> in the submodule.")
            callToAction = linkify(translate("Diff", "[Open] the submodule to commit the changes, or [discard] them."),
                                   url1, url2)
            text3.append(f"<p>{lead}<br>{callToAction}</p>")

        linkText = translate("Diff", "Open submodule {0}").format(bquo(shortName))

        text1 = translate("Diff", "Submodule {0} was updated.").format(bquo(shortName))
        text2 = linkify(linkText, url1)
        text3 = ulList(text3, -1)

        return SpecialDiffError(message=text1, details=text2, longform=text3)
