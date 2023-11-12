from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *


class ComposePatch(RepoTask):
    def effects(self):
        return TaskEffects.Nothing

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
            yield from self._flowAbort(self.tr("Nothing to export. The patch is empty."), icon="information")

        qfd = PersistentFileDialog.saveFile(self.parentWidget(), "SaveFile", self.name(), fileName)
        yield from self._flowDialog(qfd)
        savePath = qfd.selectedFiles()[0]

        yield from self._flowBeginWorkerThread()
        with open(savePath, "wb") as f:
            f.write(composed)


class ExportCommitAsPatch(ComposePatch):
    def flow(self, oid: Oid):
        yield from self._flowBeginWorkerThread()

        diffs = self.repo.commit_diffs(oid, show_binary=True)

        commit = self.repo.peel_commit(oid)
        summary, _ = messageSummary(commit.message, elision="")
        summary = "".join(c for c in summary if c.isalnum() or c in " ._-")
        summary = summary.strip()[:50].strip()
        initialName = f"{self.repo.repo_name()} {shortHash(oid)} - {summary}.patch"

        yield from self.composePatch(diffs, initialName)


class ExportStashAsPatch(ExportCommitAsPatch):
    def flow(self, oid: Oid):
        yield from self._flowBeginWorkerThread()

        diffs = self.repo.commit_diffs(oid, show_binary=True)

        commit = self.repo.peel_commit(oid)
        coreMessage = strip_stash_message(commit.message)

        initialName = f"{self.repo.repo_name()} - {coreMessage} [stashed on {shortHash(commit.parent_ids[0])}].patch"

        yield from self.composePatch(diffs, initialName)


class ExportWorkdirAsPatch(ComposePatch):
    def flow(self):
        yield from self._flowBeginWorkerThread()

        diff = self.repo.get_uncommitted_changes(show_binary=True)

        headOid = self.repo.head_commit_oid
        initialName = f"{self.repo.repo_name()} - uncommitted changes on {shortHash(headOid)}.patch"

        yield from self.composePatch([diff], initialName)
