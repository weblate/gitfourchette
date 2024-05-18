from gitfourchette.tasks.repotask import RepoTask, RepoTaskRunner, TaskPrereqs, TaskEffects
from gitfourchette.tasks.repotask import RepoGoneError
from gitfourchette.tasks.repotask import TaskInvoker

from gitfourchette.tasks.branchtasks import (
    DeleteBranch,
    DeleteBranchFolder,
    EditUpstreamBranch,
    FastForwardBranch,
    MergeBranch,
    NewBranchFromCommit,
    NewBranchFromHead,
    NewBranchFromRef,
    RecallCommit,
    RenameBranch,
    RenameBranchFolder,
    SwitchBranch,
)
from gitfourchette.tasks.committasks import NewCommit, AmendCommit, CheckoutCommit, RevertCommit, ResetHead
from gitfourchette.tasks.committasks import SetUpIdentityFirstRun, SetUpRepoIdentity
from gitfourchette.tasks.committasks import NewTag, DeleteTag
from gitfourchette.tasks.committasks import CherrypickCommit
from gitfourchette.tasks.exporttasks import (
    ExportCommitAsPatch,
    ExportPatchCollection,
    ExportStashAsPatch,
    ExportWorkdirAsPatch,
)
from gitfourchette.tasks.jumptasks import Jump, JumpBackOrForward, JumpBack, JumpForward, RefreshRepo
from gitfourchette.tasks.loadtasks import PrimeRepo
from gitfourchette.tasks.loadtasks import LoadWorkdir, LoadCommit, LoadPatch
from gitfourchette.tasks.nettasks import DeleteRemoteBranch, RenameRemoteBranch
from gitfourchette.tasks.nettasks import FetchRemote, FetchRemoteBranch
from gitfourchette.tasks.nettasks import PullBranch
from gitfourchette.tasks.nettasks import UpdateSubmodule
from gitfourchette.tasks.remotetasks import NewRemote, EditRemote, DeleteRemote
from gitfourchette.tasks.indextasks import StageFiles, UnstageFiles, DiscardFiles
from gitfourchette.tasks.indextasks import UnstageModeChanges, DiscardModeChanges
from gitfourchette.tasks.indextasks import ApplyPatch, RevertPatch
from gitfourchette.tasks.indextasks import HardSolveConflicts, MarkConflictSolved, AcceptMergeConflictResolution
from gitfourchette.tasks.indextasks import ApplyPatchFile, ApplyPatchFileReverse
from gitfourchette.tasks.indextasks import AbortMerge
from gitfourchette.tasks.stashtasks import NewStash, ApplyStash, DropStash
from gitfourchette.tasks.submoduletasks import AbsorbSubmodule, RemoveSubmodule

from gitfourchette.tasks.taskbook import TaskBook
