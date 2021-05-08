import enum


@enum.unique
class StagingState(enum.IntEnum):
    """
    State of a patch in the staging pipeline
    """

    UNTRACKED = 1
    UNSTAGED = 2
    STAGED = 3
    COMMITTED = 4

    def isDirty(self):
        return self == StagingState.UNTRACKED or self == StagingState.UNSTAGED

    def allowsRawFileAccess(self):
        return self != StagingState.COMMITTED
