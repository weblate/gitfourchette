from dataclasses import dataclass
from graphgenerator import LaneFrame


@dataclass
class CommitMetadata:
    # -------------------------------------------------------------------------
    # Immutable attributes

    hexsha: str

    author: str = ""

    authorEmail: str = ""

    authorTimestamp: int = 0

    body: str = ""

    parentHashes: list[str] = None

    # -------------------------------------------------------------------------
    # Attributes that may change as the repository evolves

    mainRefName: str = None

    laneFrame: LaneFrame = None

    bold: bool = False

    hasLocal: bool = True

    debugPrefix: str = None

    batchID: int = 0

    offsetInBatch: int = 0

