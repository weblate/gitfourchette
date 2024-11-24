# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""
Remote access tasks.
"""

import logging
import traceback
from contextlib import suppress

from gitfourchette.forms.pushdialog import PushDialog
from gitfourchette.forms.remotelinkdialog import RemoteLinkDialog
from gitfourchette.forms.textinputdialog import TextInputDialog
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.tasks import TaskPrereqs
from gitfourchette.tasks.branchtasks import MergeBranch
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables


logger = logging.getLogger(__name__)


class _BaseNetTask(RepoTask):
    remoteLinkDialog: RemoteLinkDialog | None

    def __init__(self, parent):
        super().__init__(parent)
        self.remoteLinkDialog = None

    def _showRemoteLinkDialog(self, title: str = ""):
        assert not self.remoteLinkDialog
        assert onAppThread()
        self.remoteLinkDialog = RemoteLinkDialog(title, self.parentWidget())

    def cleanup(self):
        assert onAppThread()
        if self.remoteLinkDialog:
            self.remoteLinkDialog.close()
            self.remoteLinkDialog.deleteLater()
            self.remoteLinkDialog = None

    @property
    def remoteLink(self) -> RemoteLink:
        assert self.remoteLinkDialog is not None, "can't get RemoteLink without a RemoteLinkDialog"
        return self.remoteLinkDialog.remoteLink

    def _autoDetectUpstream(self, noUpstreamMessage: str = ""):
        branchName = self.repo.head_branch_shorthand
        branch = self.repo.branches.local[branchName]

        if not branch.upstream:
            message = noUpstreamMessage or tr("Can’t fetch new commits on {0} because this branch isn’t tracking an upstream branch.")
            message = message.format(bquoe(branch.shorthand))
            raise AbortTask(message)

        return branch.upstream


class DeleteRemoteBranch(_BaseNetTask):
    def flow(self, remoteBranchShorthand: str):
        assert not remoteBranchShorthand.startswith(RefPrefix.REMOTES)

        remoteName, _ = split_remote_branch_shorthand(remoteBranchShorthand)

        text = paragraphs(
            self.tr("Really delete branch {0} from the remote repository?"),
            self.tr("The remote branch will disappear for all users of remote {1}.")
            + " " + tr("This cannot be undone!")
        ).format(bquo(remoteBranchShorthand), bquo(remoteName))
        verb = self.tr("Delete on remote")
        yield from self.flowConfirm(text=text, verb=verb, buttonIcon="SP_DialogDiscardButton")

        self._showRemoteLinkDialog()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Remotes | TaskEffects.Refs

        remote = self.repo.remotes[remoteName]
        with self.remoteLink.remoteContext(remote):
            self.repo.delete_remote_branch(remoteBranchShorthand, self.remoteLink)

        self.postStatus = self.tr("Remote branch {0} deleted.").format(tquo(remoteBranchShorthand))


class RenameRemoteBranch(_BaseNetTask):
    def flow(self, remoteBranchName: str):
        assert not remoteBranchName.startswith(RefPrefix.REMOTES)
        remoteName, branchName = split_remote_branch_shorthand(remoteBranchName)
        newBranchName = branchName  # naked name, NOT prefixed with the name of the remote

        reservedNames = self.repo.listall_remote_branches().get(remoteName, [])
        with suppress(ValueError):
            reservedNames.remove(branchName)
        nameTaken = self.tr("This name is already taken by another branch on this remote.")

        dlg = TextInputDialog(
            self.parentWidget(),
            self.tr("Rename remote branch {0}").format(tquoe(remoteBranchName)),
            self.tr("WARNING: This will rename the branch for all users of the remote!") + "<br>" + self.tr("Enter new name:"))
        dlg.setText(newBranchName)
        dlg.setValidator(lambda name: nameValidationMessage(name, reservedNames, nameTaken))
        dlg.okButton.setText(self.tr("Rename on remote"))

        yield from self.flowDialog(dlg)
        dlg.deleteLater()

        # Naked name, NOT prefixed with the name of the remote
        newBranchName = dlg.lineEdit.text()

        self._showRemoteLinkDialog(self.name())

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Remotes | TaskEffects.Refs

        remote: Remote = self.repo.remotes[remoteName]

        # Fetch remote branch first to avoid data loss if we're out of date
        with self.remoteLink.remoteContext(remote):
            self.repo.fetch_remote_branch(remoteBranchName, self.remoteLink)

        # Rename the remote branch
        # TODO: Can we reuse the connection in a single remoteContext?
        with self.remoteLink.remoteContext(remote):
            self.repo.rename_remote_branch(remoteBranchName, newBranchName, self.remoteLink)

        self.postStatus = self.tr("Remote branch {0} renamed to {1}."
                                  ).format(tquo(remoteBranchName), tquo(newBranchName))

class FetchRemotes(_BaseNetTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoDetached

    def flow(self, singleRemoteName: str = ""):
        remotes: list[Remote] = list(self.repo.remotes)

        if len(remotes) == 0:
            text = paragraphs(
                self.tr("To fetch remote branches, you must first add a remote to your repo."),
                self.tr("You can do so via <i>“Repo &rarr; Add Remote”</i>."))
            raise AbortTask(text)

        if singleRemoteName:
            remotes = [next(r for r in remotes if r.name == singleRemoteName)]

        if len(remotes) == 1:
            title = self.tr("Fetch remote {0}").format(lquo(remotes[0].name))
        else:
            title = self.tr("Fetch %n remotes", "", len(remotes))

        self._showRemoteLinkDialog(title)

        errors = []
        for remote in remotes:
            # Bail if user clicked Abort button
            yield from self.flowEnterUiThread()
            assert onAppThread()
            if self.remoteLink.isAborting():
                break

            remoteName = remote.name

            self.effects |= TaskEffects.Remotes | TaskEffects.Refs
            yield from self.flowEnterWorkerThread()
            try:
                with self.remoteLink.remoteContext(remote):
                    self.repo.fetch_remote(remoteName, self.remoteLink)
            except Exception as e:
                errors.append(f"<p><b>{escape(remoteName)}</b> — {TrTables.exceptionName(e)}.<br>{escape(str(e))}</p>")

        yield from self.flowEnterUiThread()
        self.postStatus = self.remoteLink.formatUpdatedTipsMessage(self.tr("Fetch complete."))

        # Clean up RemoteLinkDialog before showing any error text
        self.cleanup()

        if errors:
            errorMessage = self.tr("Couldn’t fetch %n remotes:", "", len(errors))
            yield from self.flowConfirm(title, errorMessage, detailList=errors, canCancel=False, icon='warning')


class FetchRemoteBranch(_BaseNetTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoDetached

    def flow(self, remoteBranchName: str = "", debrief: bool = True):
        if not remoteBranchName:
            upstream = self._autoDetectUpstream()
            remoteBranchName = upstream.shorthand

        title = self.tr("Fetch remote branch {0}").format(tquoe(remoteBranchName))
        self._showRemoteLinkDialog(title)

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Remotes | TaskEffects.Refs

        remoteName, _ = split_remote_branch_shorthand(remoteBranchName)
        remote = self.repo.remotes[remoteName]

        oldTarget = NULL_OID
        newTarget = NULL_OID
        with suppress(KeyError):
            oldTarget = self.repo.branches.remote[remoteBranchName].target

        with self.remoteLink.remoteContext(remote):
            self.repo.fetch_remote_branch(remoteBranchName, self.remoteLink)

        with suppress(KeyError):
            newTarget = self.repo.branches.remote[remoteBranchName].target

        yield from self.flowEnterUiThread()
        self.postStatus = self.remoteLink.formatUpdatedTipsMessage(
            self.tr("Fetch complete."), noNewCommits=self.tr("No new commits on {0}.").format(lquo(remoteBranchName)))

        # Jump to new commit (if branch didn't vanish)
        if oldTarget != newTarget and newTarget != NULL_OID:
            self.jumpTo = NavLocator.inCommit(newTarget)

        # Clean up RemoteLinkDialog before showing any error text
        self.cleanup()

        if newTarget == NULL_OID:
            # Raise exception to prevent PullBranch from continuing
            raise AbortTask(self.tr("{0} has disappeared from the remote server.").format(bquoe(remoteBranchName)))


class PullBranch(_BaseNetTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoDetached

    def flow(self):
        noUpstreamMessage = self.tr("Can’t pull new commits into {0} because this branch isn’t tracking an upstream branch.")
        upstreamBranch = self._autoDetectUpstream(noUpstreamMessage)

        yield from self.flowSubtask(FetchRemoteBranch, debrief=False)
        yield from self.flowSubtask(MergeBranch, upstreamBranch.name)


class UpdateSubmodule(_BaseNetTask):
    def flow(self, submoduleName: str, init=True):
        self._showRemoteLinkDialog()
        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        repo = self.repo
        submodule = repo.submodules[submoduleName]
        submodulePath = submodule.path

        if repo.restore_submodule_gitlink(submodulePath):
            with RepoContext(repo.in_workdir(submodulePath)) as subrepo:
                tree = subrepo[submodule.head_id].peel(Tree)
                subrepo.checkout_tree(tree)

        # Wrap update operation with RemoteLinkKeyFileContext: we need the keys
        # if the submodule uses an SSH connection.
        with self.remoteLink.remoteContext(submodule.url or ""):
            submodule.update(init=init, callbacks=self.remoteLink)

        self.postStatus = self.tr("Submodule updated.")


class UpdateSubmodulesRecursive(_BaseNetTask):
    def flow(self):
        count = 0

        for submodule in self.repo.recurse_submodules():
            count += 1
            yield from self.flowSubtask(UpdateSubmodule, submodule.name)

        self.postStatus = self.tr("%n submodules updated.", "", count)


class PushRefspecs(_BaseNetTask):
    def flow(self, remoteName: str, refspecs: list[str]):
        assert remoteName
        assert type(remoteName) is str
        assert type(refspecs) is list

        if remoteName == "*":
            remotes = list(self.repo.remotes)
        else:
            remotes = [self.repo.remotes[remoteName]]

        self._showRemoteLinkDialog()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs

        for remote in remotes:
            with self.remoteLink.remoteContext(remote):
                remote.push(refspecs, callbacks=self.remoteLink)


class PushBranch(RepoTask):
    def flow(self, branchName: str = ""):
        if len(self.repo.remotes) == 0:
            text = paragraphs(
                self.tr("To push a local branch to a remote, you must first add a remote to your repo."),
                self.tr("You can do so via <i>“Repo &rarr; Add Remote”</i>."))
            raise AbortTask(text)

        try:
            if not branchName:
                branchName = self.repo.head_branch_shorthand
            branch = self.repo.branches.local[branchName]
        except (GitError, KeyError) as exc:
            raise AbortTask(tr("Please switch to a local branch before performing this action.")) from exc

        dialog = PushDialog(self.repo, branch, self.parentWidget())
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        tryAgain = True
        while tryAgain:
            tryAgain = yield from self.attempt(dialog)

        dialog.accept()

    def attempt(self, dialog: PushDialog):
        yield from self.flowDialog(dialog, proceedSignal=dialog.startOperationButton.clicked)

        # ---------------
        # Push clicked

        remote = self.repo.remotes[dialog.currentRemoteName]
        logger.info(f"Will push to: {dialog.refspec} ({remote.name})")
        link = RemoteLink(self)

        dialog.ui.statusForm.initProgress(self.tr("Contacting remote host..."))
        link.message.connect(dialog.ui.statusForm.setProgressMessage)
        link.progress.connect(dialog.ui.statusForm.setProgressValue)

        if dialog.ui.trackCheckBox.isEnabled() and dialog.ui.trackCheckBox.isChecked():
            resetTrackingReference = dialog.currentRemoteBranchFullName
        else:
            resetTrackingReference = None

        # Look at the state of the checkboxes BEFORE calling this --  it'll disable the checkboxes!
        dialog.setRemoteLink(link)

        # ----------------
        # Task meat

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs

        error = None
        try:
            with link.remoteContext(remote):
                remote.push([dialog.refspec], callbacks=link)
            if resetTrackingReference:
                self.repo.edit_upstream_branch(dialog.currentLocalBranchName, resetTrackingReference)
        except Exception as exc:
            error = exc

        # ---------------
        # Debrief

        yield from self.flowEnterUiThread()
        dialog.setRemoteLink(None)
        link.deleteLater()

        if error:
            traceback.print_exception(error)
            QApplication.beep()
            QApplication.alert(dialog, 500)
            dialog.ui.statusForm.setBlurb(F"<b>{TrTables.exceptionName(error)}:</b> {escape(str(error))}")
        else:
            self.postStatus = link.formatUpdatedTipsMessage(self.tr("Push complete."))

        return bool(error)
