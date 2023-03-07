from gitfourchette.tasks.repotask import RepoTask, RepoTaskRunner, TaskAffectsWhat

from gitfourchette.tasks.branchtasks import NewTrackingBranch, EditTrackedBranch
from gitfourchette.tasks.branchtasks import NewBranchFromHead, SwitchBranch, RenameBranch, DeleteBranch
from gitfourchette.tasks.branchtasks import NewBranchFromLocalBranch, NewBranchFromCommit
from gitfourchette.tasks.branchtasks import FastForwardBranch
from gitfourchette.tasks.branchtasks import RecallCommit
from gitfourchette.tasks.committasks import NewCommit, AmendCommit, CheckoutCommit, RevertCommit, ResetHead
from gitfourchette.tasks.committasks import SetUpIdentityFirstRun, SetUpRepoIdentity
from gitfourchette.tasks.exporttasks import ExportCommitAsPatch, ExportStashAsPatch, ExportWorkdirAsPatch
from gitfourchette.tasks.loadtasks import LoadWorkdirDiffs, LoadCommit, LoadPatch
from gitfourchette.tasks.nettasks import DeleteRemoteBranch, RenameRemoteBranch
from gitfourchette.tasks.nettasks import FetchRemote, FetchRemoteBranch
from gitfourchette.tasks.remotetasks import NewRemote, EditRemote, DeleteRemote
from gitfourchette.tasks.stagetasks import StageFiles, UnstageFiles, DiscardFiles
from gitfourchette.tasks.stagetasks import ApplyPatch, RevertPatch
from gitfourchette.tasks.stagetasks import HardSolveConflict, MarkConflictSolved
from gitfourchette.tasks.stagetasks import ApplyPatchFile
from gitfourchette.tasks.stashtasks import NewStash, ApplyStash, PopStash, DropStash
