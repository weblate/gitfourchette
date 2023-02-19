from gitfourchette.tasks.repotask import RepoTask, RepoTaskRunner, TaskAffectsWhat

from gitfourchette.tasks.branchtasks import NewTrackingBranch, EditTrackedBranch
from gitfourchette.tasks.branchtasks import NewBranch, SwitchBranch, RenameBranch, DeleteBranch
from gitfourchette.tasks.branchtasks import NewBranchFromLocalBranch, NewBranchFromCommit
from gitfourchette.tasks.branchtasks import PullBranch
from gitfourchette.tasks.committasks import NewCommit, AmendCommit, CheckoutCommit, RevertCommit, ResetHead
from gitfourchette.tasks.nettasks import DeleteRemoteBranch, RenameRemoteBranch
from gitfourchette.tasks.nettasks import FetchRemote, FetchRemoteBranch
from gitfourchette.tasks.remotetasks import NewRemote, EditRemote, DeleteRemote
from gitfourchette.tasks.stagetasks import StageFiles, UnstageFiles, DiscardFiles
from gitfourchette.tasks.stashtasks import NewStash, ApplyStash, PopStash, DropStash
