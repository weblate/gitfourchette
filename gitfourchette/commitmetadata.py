from dataclasses import dataclass


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

    parentHashes: list[str] = None

    # -------------------------------------------------------------------------
    # Attributes that may change as the repository evolves

    childHashes: list[str] = None

    mainRefName: str = None

    bold: bool = False

    hasLocal: bool = True

    debugPrefix: str = None

    batchID: int = 0

    offsetInBatch: int = 0

