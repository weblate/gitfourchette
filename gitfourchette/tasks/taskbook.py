from __future__ import annotations

import logging
from typing import Any, Type, Union

from gitfourchette import tasks
from gitfourchette.qt import *
from gitfourchette.settings import DEVDEBUG
from gitfourchette.tasks import RepoTask, TaskInvoker
from gitfourchette.toolbox import stockIcon, MultiShortcut, makeMultiShortcut, appendShortcutToToolTipText

logger = logging.getLogger(__name__)


class TaskBook:
    """ Registry of metadata about task commands """

    names: dict[Type[RepoTask], str] = {}
    toolbarNames: dict[Type[RepoTask], str] = {}
    tips: dict[Type[RepoTask], str] = {}
    shortcuts: dict[Type[RepoTask], MultiShortcut] = {}
    icons: dict[Type[RepoTask], Union[str, int]] = {}
    noEllipsis: set[Type[RepoTask]]

    @classmethod
    def initialize(cls):
        cls.names = {
            tasks.AbortMerge: translate("task", "Abort merge"),
            tasks.AbsorbSubmodule: translate("task", "Absorb existing repo as submodule"),
            tasks.AcceptMergeConflictResolution: translate("task", "Accept merge conflict resolution"),
            tasks.AmendCommit: translate("task", "Amend last commit"),
            tasks.ApplyPatch: translate("task", "Apply selected text", "partial patch from selected text in diff"),
            tasks.ApplyPatchFile: translate("task", "Apply patch file"),
            tasks.ApplyPatchFileReverse: translate("task", "Reverse patch file"),
            tasks.ApplyStash: translate("task", "Apply stash"),
            tasks.CheckoutCommit: translate("task", "Check out commit"),
            tasks.CherrypickCommit: translate("task", "Cherry-pick"),
            tasks.DeleteBranch: translate("task", "Delete local branch"),
            tasks.DeleteRemote: translate("task", "Remove remote"),
            tasks.DeleteRemoteBranch: translate("task", "Delete branch on remote"),
            tasks.DeleteTag: translate("task", "Delete tag"),
            tasks.DiscardFiles: translate("task", "Discard files"),
            tasks.DiscardModeChanges: translate("task", "Discard mode changes"),
            tasks.DropStash: translate("task", "Drop stash"),
            tasks.EditRemote: translate("task", "Edit remote"),
            tasks.EditUpstreamBranch: translate("task", "Edit upstream branch"),
            tasks.ExportCommitAsPatch: translate("task", "Export commit as patch file"),
            tasks.ExportStashAsPatch: translate("task", "Export stash as patch file"),
            tasks.ExportWorkdirAsPatch: translate("task", "Export changes as patch file"),
            tasks.FastForwardBranch: translate("task", "Fast-forward branch"),
            tasks.FetchRemote: translate("task", "Fetch remote"),
            tasks.FetchRemoteBranch: translate("task", "Fetch remote branch"),
            tasks.HardSolveConflicts: translate("task", "Accept/reject incoming changes"),
            tasks.Jump: translate("task", "Navigate in repo"),
            tasks.JumpBack: translate("task", "Navigate back"),
            tasks.JumpBackOrForward: translate("task", "Navigate forward"),
            tasks.JumpForward: translate("task", "Navigate forward"),
            tasks.LoadCommit: translate("task", "Load commit"),
            tasks.LoadPatch: translate("task", "Load diff"),
            tasks.LoadWorkdir: translate("task", "Refresh working directory"),
            tasks.MarkConflictSolved: translate("task", "Mark conflict solved"),
            tasks.MergeBranch: translate("task", "Merge branch"),
            tasks.NewBranchFromCommit: translate("task", "New local branch"),
            tasks.NewBranchFromHead: translate("task", "New local branch"),
            tasks.NewBranchFromRef: translate("task", "New local branch"),
            tasks.NewCommit: translate("task", "Commit"),
            tasks.NewRemote: translate("task", "Add remote"),
            tasks.NewStash: translate("task", "Stash changes"),
            tasks.NewTag: translate("task", "New tag"),
            tasks.PrimeRepo: translate("task", "Open repo"),
            tasks.RecallCommit: translate("task", "Recall lost commit"),
            tasks.RefreshRepo: translate("task", "Refresh repo"),
            tasks.RemoveSubmodule: translate("task", "Remove submodule"),
            tasks.RenameBranch: translate("task", "Rename local branch"),
            tasks.RenameRemoteBranch: translate("task", "Rename branch on remote"),
            tasks.ResetHead: translate("task", "Reset HEAD"),
            tasks.RevertCommit: translate("task", "Revert commit"),
            tasks.RevertPatch: translate("task", "Revert selected text", "partial patch from selected text in diff"),
            tasks.SetUpIdentityFirstRun: translate("task", "Set up Git identity"),
            tasks.SetUpRepoIdentity: translate("task", "Set up Git identity"),
            tasks.StageFiles: translate("task", "Stage files"),
            tasks.SwitchBranch: translate("task", "Switch to branch"),
            tasks.UpdateSubmodule: translate("task", "Update submodule"),
            tasks.UnstageFiles: translate("task", "Unstage files"),
            tasks.UnstageModeChanges: translate("task", "Unstage mode changes"),
        }

        cls.toolbarNames = {
            tasks.FetchRemote: translate("task", "Fetch"),
            tasks.JumpBack: translate("task", "Back"),
            tasks.JumpForward: translate("task", "Forward"),
            tasks.NewBranchFromHead: translate("task", "Branch"),
            tasks.NewStash: translate("task", "Stash"),
        }

        cls.tips = {
            tasks.AmendCommit: translate("task", "Amend the last commit on the current branch with the staged changes in the working directory"),
            tasks.ApplyPatchFile: translate("task", "Apply a patch file to the working directory"),
            tasks.ApplyPatchFileReverse: translate("task", "Apply a patch file to the working directory (reverse patch before applying)"),
            tasks.ApplyStash: translate("task", "Restore backed up changes to the working directory"),
            tasks.CherrypickCommit: translate("task", "Bring the changes introduced by this commit to the current branch"),
            tasks.DeleteBranch: translate("task", "Delete this branch locally"),
            tasks.EditUpstreamBranch: translate("task", "Choose the remote branch to be tracked by this local branch"),
            tasks.ExportStashAsPatch: translate("task", "Create a patch file from this stash"),
            tasks.FastForwardBranch: translate("task", "Advance this local branch to the tip of the remote-tracking branch"),
            tasks.FetchRemote: translate("task", "Get the latest commits on all remote branches from the server"),
            tasks.FetchRemoteBranch: translate("task", "Get the latest commits from the remote server"),
            tasks.NewBranchFromCommit: translate("task", "Start a new branch from this commit"),
            tasks.NewBranchFromHead: translate("task", "Start a new branch from the current HEAD"),
            tasks.NewBranchFromRef: translate("task", "Start a new branch from the tip of this branch"),
            tasks.NewCommit: translate("task", "Create a commit of the staged changes in the working directory"),
            tasks.NewRemote: translate("task", "Add a remote server to this repo"),
            tasks.NewStash: translate("task", "Back up uncommitted changes and clean up the working directory"),
            tasks.NewTag: translate("task", "Tag this commit with a name"),
            tasks.RemoveSubmodule: translate("task", "Remove this submodule from .gitmodules and delete its working copy from this repo"),
            tasks.RenameBranch: translate("task", "Rename this branch locally"),
            tasks.ResetHead: translate("task", "Make HEAD point to another commit"),
            tasks.RevertCommit: translate("task", "Revert the changes introduced by this commit"),
            tasks.SetUpIdentityFirstRun: translate("task", "Set up the identity under which you create commits"),
            tasks.SetUpRepoIdentity: translate("task", "Set up the identity under which you create commits"),
            tasks.SwitchBranch: translate("task", "Switch to this branch and update the working directory to match it"),
        }

        cls.shortcuts = {
            tasks.AmendCommit: makeMultiShortcut(QKeySequence.StandardKey.SaveAs, "Ctrl+Shift+S"),
            tasks.ApplyPatchFile: makeMultiShortcut("Ctrl+I"),
            tasks.NewBranchFromHead: makeMultiShortcut("Ctrl+B"),
            tasks.NewCommit: makeMultiShortcut(QKeySequence.StandardKey.Save),
            tasks.NewStash: makeMultiShortcut("Ctrl+Alt+S"),
            tasks.JumpBack: makeMultiShortcut("Ctrl+Left" if MACOS else "Alt+Left"),
            tasks.JumpForward: makeMultiShortcut("Ctrl+Right" if MACOS else "Alt+Right"),
        }

        cls.icons = {
            tasks.AmendCommit: "document-save-as",
            tasks.DeleteBranch: "vcs-branch-delete",
            tasks.DeleteRemote: QStyle.StandardPixmap.SP_TrashIcon,
            tasks.DeleteRemoteBranch: QStyle.StandardPixmap.SP_TrashIcon,
            tasks.DeleteTag: QStyle.StandardPixmap.SP_TrashIcon,
            tasks.DropStash: QStyle.StandardPixmap.SP_TrashIcon,
            tasks.EditRemote: "document-edit",
            tasks.FastForwardBranch: "media-skip-forward",
            tasks.FetchRemote: QStyle.StandardPixmap.SP_BrowserReload,
            tasks.FetchRemoteBranch: QStyle.StandardPixmap.SP_BrowserReload,
            tasks.JumpBack: QStyle.StandardPixmap.SP_ArrowBack,
            tasks.JumpForward: QStyle.StandardPixmap.SP_ArrowForward,
            tasks.MergeBranch: "vcs-merge",
            tasks.NewBranchFromCommit: "vcs-branch",
            tasks.NewBranchFromHead: "vcs-branch",
            tasks.NewBranchFromRef: "vcs-branch",
            tasks.NewCommit: "document-save",
            tasks.NewRemote: "folder-remote",
            tasks.NewStash: "vcs-stash",
            tasks.NewTag: "tag-new",
            tasks.SetUpIdentityFirstRun: "user-identity",
            tasks.SetUpRepoIdentity: "user-identity",
            tasks.SwitchBranch: "document-swap",
        }

        cls.noEllipsis = {
            tasks.FetchRemoteBranch,
            tasks.FastForwardBranch,
            tasks.JumpBack,
            tasks.JumpForward,
        }

        # Check that all tasks have names
        if DEVDEBUG:
            for n, t in vars(tasks).items():
                try:
                    if issubclass(t, RepoTask) and t is not RepoTask and t not in cls.names:
                        logger.warning(f"Missing task name: {t.__name__}")
                except TypeError:
                    pass

    @classmethod
    def autoActionName(cls, t: Type[RepoTask]):
        assert cls.names
        try:
            name = cls.names[t]
        except KeyError:
            name = t.__name__
            cls.names[t] = name
            logger.warning(f"Missing name for task '{name}'")

        if QLocale().language() in [QLocale.Language.C, QLocale.Language.English]:
            name = name.title()
        if t not in cls.noEllipsis:
            name += "..."
        return name

    @classmethod
    def action(
            cls,
            invoker: QObject,
            taskType: Type[RepoTask],
            name="",
            enabled=True,
            menuRole=QAction.MenuRole.NoRole,
            taskArgs: Any = None
    ) -> QAction:
        if not name:
            name = cls.autoActionName(taskType)
        elif len(name) == 2 and name[0] == "&":
            accel = name[1]
            name = cls.autoActionName(taskType)
            i = name.lower().find(accel.lower())
            if i >= 0:
                name = name[:i] + "&" + name[i:]

        action = QAction()
        action.setText(name)
        action.setEnabled(bool(enabled))
        action.setMenuRole(menuRole)

        cls._fillAction(action, invoker, taskType, taskArgs)
        return action

    @classmethod
    def toolbarAction(cls, invoker: QObject, taskType: Type[RepoTask]):
        try:
            name = cls.toolbarNames[taskType]
        except KeyError:
            name = ""

        action = cls.action(invoker, taskType, name)

        tip = cls.autoActionName(taskType)
        if taskType in cls.shortcuts:
            tip = appendShortcutToToolTipText(tip, cls.shortcuts[taskType][0])
        action.setToolTip(tip)

        return action

    @classmethod
    def _fillAction(cls, action: QAction, invoker: QObject, taskType: Type[RepoTask], taskArgs=None):
        assert cls.names

        if taskType in cls.icons:
            action.setIcon(stockIcon(cls.icons[taskType]))

        if taskType in cls.shortcuts:
            action.setShortcuts(cls.shortcuts[taskType])

        if taskType in cls.tips:
            action.setStatusTip(cls.tips[taskType])

        if taskArgs is None:
            taskArgs = ()
        elif type(taskArgs) not in [tuple, list]:
            taskArgs = tuple([taskArgs])

        action.triggered.connect(lambda: TaskInvoker.invoke(invoker, taskType, *taskArgs))

        return action

