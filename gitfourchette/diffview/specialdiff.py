"""Non-textual diffs"""
from contextlib import suppress
import os
import re
from dataclasses import dataclass

from gitfourchette import settings
from gitfourchette.nav import NavLocator, NavContext, NavFlags
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
            icon: str = "SP_MessageBoxInformation",
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
    def diffTooLarge(size, threshold, locator):
        locale = QLocale()
        humanSize = locale.formattedDataSize(size, 1)
        humanThreshold = locale.formattedDataSize(threshold, 0)
        loadAnyway = locator.withExtraFlags(NavFlags.AllowLargeFiles)
        configure = makeInternalLink("prefs", "largeFileThresholdKB")
        longform = toRoomyUL([
            linkify(translate("Diff", "[Load diff anyway] (this may take a moment)"), loadAnyway.url()),
            linkify(translate("Diff", "[Configure diff preview limit] (currently: {0})"), configure).format(humanThreshold),
        ])
        return SpecialDiffError(
            translate("Diff", "This diff is too large to be previewed."),
            translate("Diff", "Diff size: {0}").format(humanSize),
            "SP_MessageBoxWarning",
            longform=longform)

    @staticmethod
    def imageTooLarge(size, threshold, locator):
        locale = QLocale()
        humanSize = locale.formattedDataSize(size, 1)
        humanThreshold = locale.formattedDataSize(threshold, 0)
        loadAnyway = locator.withExtraFlags(NavFlags.AllowLargeFiles)
        configure = makeInternalLink("prefs", "imageFileThresholdKB")
        longform = toRoomyUL([
            linkify(translate("Diff", "[Load image anyway] (this may take a moment)"), loadAnyway.url()),
            linkify(translate("Diff", "[Configure image preview limit] (currently: {0})"), configure).format(humanThreshold),
        ])
        return SpecialDiffError(
            translate("Diff", "This image is too large to be previewed."),
            translate("Diff", "Image size: {0}").format(humanSize),
            "SP_MessageBoxWarning",
            longform=longform)

    @staticmethod
    def typeChange(delta: DiffDelta):
        oldFile = delta.old_file
        newFile = delta.new_file
        oldText = translate("Diff", "Old type:")
        newText = translate("Diff", "New type:")
        oldMode = TrTables.fileMode(oldFile.mode)
        newMode = TrTables.fileMode(newFile.mode)
        table = ("<table>"
                 f"<tr><td><del><b>{oldText}</b></del> </td><td>{oldMode}</tr>"
                 f"<tr><td><add><b>{newText}</b></add> </td><td>{newMode}</td></tr>"
                 "</table>")
        return SpecialDiffError(translate("Diff", "This file’s type has changed."), table)

    @staticmethod
    def binaryDiff(delta: DiffDelta, locator: NavLocator):
        locale = QLocale()
        of = delta.old_file
        nf = delta.new_file

        if isImageFormatSupported(of.path) and isImageFormatSupported(nf.path):
            largestSize = max(of.size, nf.size)
            threshold = settings.prefs.imageFileThresholdKB * 1024
            if threshold != 0 and largestSize > threshold and not locator.hasFlags(NavFlags.AllowLargeFiles):
                return SpecialDiffError.imageTooLarge(largestSize, threshold, locator)
            else:
                return ShouldDisplayPatchAsImageDiff()
        else:
            oldHumanSize = locale.formattedDataSize(of.size)
            newHumanSize = locale.formattedDataSize(nf.size)
            return SpecialDiffError(
                translate("Diff", "File appears to be binary."),
                f"{oldHumanSize} &rarr; {newHumanSize}")

    @staticmethod
    def submoduleDiff(repo: Repo, patch: Patch, locator: NavLocator):
        from gitfourchette.tasks import DiscardFiles

        shortName = os.path.basename(patch.delta.new_file.path)
        localPath = repo.in_workdir(patch.delta.new_file.path)
        openLink = QUrl.fromLocalFile(localPath)
        stillExists = os.path.isdir(localPath)
        isDeletion = patch.delta.status == DeltaStatus.DELETED

        isHastyAdd = False
        if patch.delta.status == DeltaStatus.ADDED and locator.context == NavContext.STAGED:
            isHastyAdd = True

        if isDeletion:
            titleText = translate("Diff", "Submodule {0} was removed.")
        elif patch.delta.status == DeltaStatus.ADDED:
            titleText = translate("Diff", "Submodule {0} was added.")
        else:
            titleText = translate("Diff", "Submodule {0} was updated.")
        titleText = titleText.format(bquo(shortName))

        specialDiff = SpecialDiffError(titleText)
        longformParts = []

        oldOid, newOid, dirty = parse_submodule_patch(patch.text)
        headDidMove = oldOid != newOid

        # Create old/new table if the submodule's HEAD commit was moved
        if headDidMove and not isDeletion:
            targets = [shortHash(oldOid), shortHash(newOid)]
            messages = ["", ""]

            # Show additional details about the commits if there's still a workdir for this submo
            if stillExists:
                # Make links to specific commits
                for i, h in enumerate([oldOid, newOid]):
                    if h != NULL_OID:
                        targets[i] = linkify(shortHash(h), f"{openLink.toString()}#{h.hex}")

                # Show commit summaries
                with RepoContext(localPath, RepositoryOpenFlag.NO_SEARCH) as subRepo:
                    for i, h in enumerate([oldOid, newOid]):
                        with suppress(LookupError, GitError):
                            m = subRepo[h].peel(Commit).message
                            m = messageSummary(m)[0]
                            m = elide(m, Qt.TextElideMode.ElideRight, 25)
                            m = hquo(m)
                            messages[i] = m

            oldText = translate("Diff", "Old:")
            newText = translate("Diff", "New:")
            table = ("<table>"
                     f"<tr><td><del><b>{oldText}</b></del> </td><td><code>{targets[0]} </code> {messages[0]}</td></tr>"
                     f"<tr><td><add><b>{newText}</b></add> </td><td><code>{targets[1]} </code> {messages[1]}</td></tr>"
                     "</table>")

            if locator.context == NavContext.UNSTAGED:
                intro = translate("Diff", "<b>HEAD</b> was moved to another commit &ndash; you can stage this update:")
            else:
                intro = translate("Diff", "<b>HEAD</b> was moved to another commit:")
            longformParts.append(f"{intro}<p>{table}</p>")

        # Tell about any uncommitted changes
        if dirty:
            discardLink = specialDiff.links.new(lambda invoker: DiscardFiles.invoke(invoker, [patch]))

            if headDidMove:
                lead = translate("Diff", "In addition, there are <b>uncommitted changes</b> in the submodule.")
            else:
                lead = translate("Diff", "There are <b>uncommitted changes</b> in the submodule.")
            callToAction = linkify(translate("Diff", "[Open] the submodule to commit the changes, or [discard] them."),
                                   openLink, discardLink)
            longformParts.append(f"{lead}<br>{callToAction}")

        # Add link to open the submodule as a subtitle
        if stillExists:
            subtitle = translate("Diff", "Open submodule {0}").format(bquo(shortName))
            subtitle = linkify(subtitle, openLink)
            specialDiff.details = subtitle

        if isHastyAdd:
            text = translate(
                "Diff",
                "<b>WARNING:</b> You’ve added another Git repo inside your current repo, "
                "but this does not actually embed the contents of the inner repo. "
                "So, you should register the inner repo as a <i>submodule</i>. "
                "This way, clones of the outer repo will know how to obtain the inner repo."
            ).format(hquo(shortName), hquo(os.path.basename(repo.repo_name())))
            longformParts.insert(0, text)

        # Compile longform parts into an unordered list
        specialDiff.longform = toRoomyUL(longformParts)

        return specialDiff
