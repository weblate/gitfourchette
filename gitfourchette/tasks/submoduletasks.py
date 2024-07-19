"""
Submodule management tasks.
"""

from contextlib import suppress
from pathlib import Path

from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.registersubmoduledialog import RegisterSubmoduleDialog
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskPrereqs, TaskEffects
from gitfourchette.toolbox import *


class RegisterSubmodule(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, path: str):
        yield from self._flow(path, absorb=False)

    def _flow(self, path: str, absorb: bool):
        thisWD = Path(self.repo.workdir)
        thisName = thisWD.name
        subWD = Path(thisWD / path)
        subName = subWD.name
        subRemotes = {}

        preferredRemote = ""
        with RepoContext(thisWD / subWD) as subRepo:
            assert not subRepo.is_bare
            for remote in subRepo.remotes:
                subRemotes[remote.name] = remote.url
            with suppress(Exception):
                localBranch = subRepo.branches.local[subRepo.head_branch_shorthand]
                upstreamRemoteName = localBranch.upstream.remote_name
                preferredRemote = subRemotes[upstreamRemoteName]

        if not subRemotes:
            message = paragraphs(
                translate("RegisterSubmoduleDialog", "{0} has no remotes."),
                translate("RegisterSubmoduleDialog", "Please open {0} and add a remote to it "
                                                     "before absorbing it as a submodule.")
            ).format(bquo(subName))
            raise AbortTask(message)

        dlg = RegisterSubmoduleDialog(
            currentName="",
            fallbackName=path,
            superprojectName=thisName,
            remotes=subRemotes,
            absorb=absorb,
            parent=self.parentWidget())

        if preferredRemote:
            i = dlg.ui.remoteComboBox.findData(preferredRemote)
            if i >= 0:
                dlg.ui.remoteComboBox.setCurrentIndex(i)

        convertToBrandedDialog(dlg, subtitleText=lquo(path))
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()

        yield from self.flowDialog(dlg)

        remoteUrl = dlg.remoteUrl
        customName = dlg.customName
        dlg.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir | TaskEffects.Refs  # we don't have TaskEffects.Submodules so .Refs is the next best thing

        innerWD = str(subWD.relative_to(thisWD))
        self.repo.add_inner_repo_as_submodule(innerWD, remoteUrl, name=customName, absorb_git_dir=absorb)


class AbsorbSubmodule(RegisterSubmodule):
    def flow(self, path: str):
        yield from self._flow(path, absorb=True)


class RemoveSubmodule(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts

    def flow(self, submoduleName: str):
        yield from self.flowConfirm(
            text=paragraphs(
                self.tr("Really remove submodule {0}?"),
                self.tr("The submodule will be removed from {1} and its working copy will be deleted."),
                self.tr("Any changes in the submodule that haven’t been pushed will be lost."),
                tr("This cannot be undone!"),
            ).format(bquo(submoduleName), hquo(".gitmodules")),
            buttonIcon="SP_DialogDiscardButton",
            verb="Remove")

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir | TaskEffects.Refs  # we don't have TaskEffects.Submodules so .Refs is the next best thing

        self.repo.remove_submodule(submoduleName)
