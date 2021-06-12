"""
from dataclasses import dataclass
from pygit2 import Oid


@dataclass
class CommitMetadata:
    # -------------------------------------------------------------------------
    # Immutable attributes

    hexsha: str

    isInitialized: bool = False

    author: str = ""

    authorEmail: str = ""

    authorTimestamp: int = 0

    body: str = ""

    parentIds: list[Oid] = None

    # -------------------------------------------------------------------------
    # Attributes that may change as the repository evolves

    childIds: list[Oid] = None

    mainRefName: str = None

    bold: bool = False

    hasLocal: bool = True

    debugPrefix: str = None

    batchID: int = 0

    offsetInBatch: int = 0
"""

