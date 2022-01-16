import tempfile

# The directory is deleted when the program exits.
tempdir: tempfile.TemporaryDirectory | None = None


def getSessionTemporaryDirectory():
    """Returns the path to the temporary directory for this session. Creates one if needed."""

    global tempdir

    if not tempdir:
        tempdir = tempfile.TemporaryDirectory(prefix="GitFourchette-", ignore_cleanup_errors=True)

    return tempdir.name
