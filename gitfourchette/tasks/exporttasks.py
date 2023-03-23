from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
import contextlib
import html
import pygit2


class ComposePatch(RepoTask):
    def name(self):
        return translate("Operation", "Export patch file")

    def refreshWhat(self):
        return TaskAffectsWhat.NOTHING

    def composePatch(self, diffs, fileName):
        yield from self._flowBeginWorkerThread()

        composed = b""

        for diff in diffs:
            # QThread.yieldCurrentThread()
            for patch in diff:
                if not patch:
                    continue
                diffPatchData = patch.data
                composed += diffPatchData
                assert composed.endswith(b"\n")

        yield from self._flowExitWorkerThread()

        if not composed:
            yield from self._flowAbort(self.tr("Nothing to export. The patch is empty."), warningTextIcon="information")

        qfd = util.PersistentFileDialog.saveFile(self.parentWidget(), "SaveFile", self.name(), fileName)
        yield from self._flowDialog(qfd)
        savePath = qfd.selectedFiles()[0]

        yield from self._flowBeginWorkerThread()
        with open(savePath, "wb") as f:
            f.write(composed)


class ExportCommitAsPatch(ComposePatch):
    def name(self):
        return translate("Operation", "Export commit as patch file")

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()

        diffs = porcelain.loadCommitDiffs(self.repo, oid, showBinary=True)

        commit: pygit2.Commit = self.repo[oid].peel(pygit2.Commit)
        summary, _ = util.messageSummary(commit.message, elision="")
        summary = "".join(c for c in summary if c.isalnum() or c in " ._-")
        summary = summary.strip()[:50].strip()
        initialName = f"{porcelain.repoName(self.repo)} {util.shortHash(oid)} - {summary}.patch"

        yield from self.composePatch(diffs, initialName)


class ExportStashAsPatch(ExportCommitAsPatch):
    def name(self):
        return translate("Operation", "Export stash as patch file")

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()

        diffs = porcelain.loadCommitDiffs(self.repo, oid, showBinary=True)

        commit: pygit2.Commit = self.repo[oid].peel(pygit2.Commit)
        coreMessage = porcelain.getCoreStashMessage(commit.message)

        initialName = f"{porcelain.repoName(self.repo)} - {coreMessage} [stashed on {util.shortHash(commit.parent_ids[0])}].patch"

        yield from self.composePatch(diffs, initialName)


class ExportWorkdirAsPatch(ComposePatch):
    def name(self):
        return translate("Operation", "Export uncommitted changes as patch file")

    def flow(self):
        yield from self._flowBeginWorkerThread()

        diff = porcelain.getWorkdirChanges(self.repo, showBinary=True)

        headOid = porcelain.getHeadCommitOid(self.repo)
        initialName = f"{porcelain.repoName(self.repo)} - uncommitted changes on {util.shortHash(headOid)}.patch"

        yield from self.composePatch([diff], initialName)
