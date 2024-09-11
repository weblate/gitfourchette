"""Non-textual diffs"""
from contextlib import suppress
import os

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
                return SpecialDiffError.treeDiff(delta)
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
    def treeDiff(delta):
        from gitfourchette.tasks import AbsorbSubmodule

        treePath = os.path.normpath(delta.new_file.path)
        treeName = os.path.basename(treePath)
        message = translate("Diff", "This untracked folder is the root of another Git repository.")

        # TODO: if we had the full path to the root repo, we could just make a standard file link, and we wouldn't need the "opensubfolder" authority
        prompt1 = translate("Diff", "Open {0}").format(bquo(treeName))
        openLink = makeInternalLink("opensubfolder", treePath)

        prompt2 = translate("Diff", "Absorb {0} as submodule").format(bquo(treeName))
        prompt2 = translate("Diff", "Recommended action:") + " [" + prompt2 + "]"
        taskLink = AbsorbSubmodule.makeInternalLink(path=treePath)

        return SpecialDiffError(
            message,
            linkify(prompt1, openLink),
            longform=toRoomyUL([linkify(prompt2, taskLink)]))

    @staticmethod
    def submoduleDiff(repo: Repo, patch: Patch, locator: NavLocator):
        from gitfourchette.tasks.indextasks import DiscardFiles

        smDiff = repo.get_submodule_diff(patch, in_workdir=locator.context.isWorkdir())
        openLink = QUrl.fromLocalFile(smDiff.workdir)

        if smDiff.is_del:
            titleText = translate("Diff", "Submodule {0} was [removed.]")
            titleText = tagify(titleText, "<del><b>")
        elif smDiff.is_add:
            titleText = translate("Diff", "Submodule {0} was [added.]")
            titleText = tagify(titleText, "<add><b>")
        elif smDiff.head_did_move:
            titleText = translate("Diff", "Submodule {0} was updated.")
        else:
            titleText = translate("Diff", "Submodule {0} contains changes.")
        titleText = titleText.format(bquo(smDiff.short_name))

        specialDiff = SpecialDiffError(titleText)
        longformParts = []

        # Create old/new table if the submodule's HEAD commit was moved
        if smDiff.head_did_move and not smDiff.is_del:
            targets = [shortHash(smDiff.old_id), shortHash(smDiff.new_id)]
            messages = ["", ""]

            # Show additional details about the commits if there's still a workdir for this submo
            if smDiff.still_exists:
                try:
                    with RepoContext(smDiff.workdir, RepositoryOpenFlag.NO_SEARCH) as subRepo:
                        for i, h in enumerate([smDiff.old_id, smDiff.new_id]):
                            if h == NULL_OID:
                                continue

                            # Link to specific commit
                            targets[i] = linkify(shortHash(h), f"{openLink.toString()}#{h}")

                            # Get commit summary
                            with suppress(LookupError, GitError):
                                m = subRepo[h].peel(Commit).message
                                m = messageSummary(m)[0]
                                m = elide(m, Qt.TextElideMode.ElideRight, 25)
                                m = hquo(m)
                                messages[i] = m
                except GitError:
                    # RepoContext may fail if the submodule couldn't be opened for any reason.
                    # Don't show an error for this, show the diff document anyway
                    pass

            oldText = translate("Diff", "Old:")
            newText = translate("Diff", "New:")
            table = ("<table>"
                     f"<tr><td><del><b>{oldText}</b></del> </td><td><code>{targets[0]} </code> {messages[0]}</td></tr>"
                     f"<tr><td><add><b>{newText}</b></add> </td><td><code>{targets[1]} </code> {messages[1]}</td></tr>"
                     "</table>")

            if locator.context == NavContext.UNSTAGED:
                intro = translate("Diff", "The submodule’s <b>HEAD</b> has moved to another commit &ndash; you can stage this update:")
            else:
                intro = translate("Diff", "The submodule’s <b>HEAD</b> has moved to another commit:")
            longformParts.append(f"{intro}<p>{table}</p>")

        if locator.context.isWorkdir():
            from gitfourchette.tasks import AbsorbSubmodule, RegisterSubmodule
            gitmodulesTag = "<tt>.gitmodules</tt>"

            m = ""
            if smDiff.is_del:
                if smDiff.is_registered:
                    m = translate("Diff", "To complete the removal of this submodule, "
                                          "<b>remove it from {0}</b>.").format(gitmodulesTag)
                else:
                    m = translate("Diff", "To complete the removal of this submodule, "
                                          "make sure to commit <b>{0}</b> at the same time "
                                          "as the submodule folder itself.").format(gitmodulesTag)

            elif smDiff.is_registered and not smDiff.was_registered:
                m = translate("Diff", "To complete the addition of this submodule, "
                                      "make sure to <b>commit {0}</b> at the same time "
                                      "as the submodule folder itself.").format(gitmodulesTag)

            elif not smDiff.is_absorbed:
                m = translate("Diff", "To complete the addition of this submodule, "
                                      "you should [absorb the submodule] into the parent repository.")
                m = linkify(m, AbsorbSubmodule.makeInternalLink(path=patch.delta.new_file.path))

            elif not smDiff.is_registered:
                m = translate("Diff", "To complete the addition of this submodule, "
                                      "[register it in {0}].").format(gitmodulesTag)
                m = linkify(m, RegisterSubmodule.makeInternalLink(path=patch.delta.new_file.path))

            if m:
                important = translate("Diff", "IMPORTANT")
                m = f"<img src='assets:icons/achtung'> <b>{important}</b> &ndash; {m}"
                longformParts.insert(0, m)

            # Tell about any uncommitted changes
            if smDiff.dirty:
                discardLink = specialDiff.links.new(lambda invoker: DiscardFiles.invoke(invoker, [patch]))

                m = translate("Diff", "The submodule has <b>uncommitted changes</b>. "
                                      "They can’t be committed from the parent repo. You can:")
                m += "<ul>"
                m += "<li>" + translate("Diff", "[Open] the submodule and commit the changes.")
                m += "<li>" + translate("Diff", "Or, [Reset] the submodule to a clean state.")
                m += "</ul>"
                m = linkify(m, openLink, discardLink)
                longformParts.append(m)

        # Add link to open the submodule as a subtitle
        if smDiff.still_exists:
            subtitle = translate("Diff", "Open submodule")
            if smDiff.short_name != patch.delta.new_file.path:
                subtitle += " " + translate("Diff", "(path: {0})").format(escape(patch.delta.new_file.path))
            subtitle = linkify(subtitle, openLink)
            specialDiff.details = subtitle

        # Compile longform parts into an unordered list
        specialDiff.longform = toRoomyUL(longformParts)

        return specialDiff
