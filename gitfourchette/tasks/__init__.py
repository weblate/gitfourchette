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
    ResetHead,
    SwitchBranch,
)
from gitfourchette.tasks.committasks import (
    AmendCommit,
    CheckoutCommit,
    CherrypickCommit,
    DeleteTag,
    NewCommit,
    NewTag,
    RevertCommit,
    SetUpGitIdentity,
)
from gitfourchette.tasks.exporttasks import (
    ExportCommitAsPatch,
    ExportPatchCollection,
    ExportStashAsPatch,
    ExportWorkdirAsPatch,
)
from gitfourchette.tasks.misctasks import (
    EditRepoSettings,
    GetCommitInfo,
)
from gitfourchette.tasks.jumptasks import Jump, JumpBackOrForward, JumpBack, JumpForward, RefreshRepo
from gitfourchette.tasks.loadtasks import PrimeRepo
from gitfourchette.tasks.loadtasks import LoadWorkdir, LoadCommit, LoadPatch
from gitfourchette.tasks.nettasks import DeleteRemoteBranch, RenameRemoteBranch
from gitfourchette.tasks.nettasks import FetchRemote, FetchRemoteBranch
from gitfourchette.tasks.nettasks import PullBranch
from gitfourchette.tasks.nettasks import UpdateSubmodule
from gitfourchette.tasks.remotetasks import NewRemote, EditRemote, DeleteRemote

from gitfourchette.tasks.indextasks import (
    AbortMerge,
    AcceptMergeConflictResolution,
    ApplyPatch,
    ApplyPatchFile,
    ApplyPatchFileReverse,
    DiscardFiles,
    DiscardModeChanges,
    HardSolveConflicts,
    MarkConflictSolved,
    RevertPatch,
    ApplyPatchData,
    StageFiles,
    UnstageFiles,
    UnstageModeChanges,
)

from gitfourchette.tasks.stashtasks import (
    ApplyStash,
    DropStash,
    NewStash,
)

from gitfourchette.tasks.submoduletasks import (
    AbsorbSubmodule,
    RegisterSubmodule,
    RemoveSubmodule,
)

from gitfourchette.tasks.taskbook import TaskBook
