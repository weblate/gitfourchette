from dataclasses import dataclass
import enum
import pygit2


@dataclass
class SidebarEntry:
    class Type(enum.IntEnum):
        UNCOMMITTED_CHANGES = enum.auto()
        LOCAL_BRANCHES_HEADER = enum.auto()
        LOCAL_REF = enum.auto()
        DETACHED_HEAD = enum.auto()
        UNBORN_HEAD = enum.auto()
        REMOTE_REF = enum.auto()
        REMOTE = enum.auto()
        TAG = enum.auto()

    type: Type
    name: str | None = None
    oid: pygit2.Oid | None = None
    trackingBranch: str | None = None

