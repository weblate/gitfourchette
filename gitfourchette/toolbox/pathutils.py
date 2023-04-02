from gitfourchette.settings import PathDisplayStyle
import os

HOME = os.path.abspath(os.path.expanduser('~'))


def compactPath(path: str) -> str:
    # Normalize path first, which also turns forward slashes to backslashes on Windows.
    path = os.path.abspath(path)
    if path.startswith(HOME):
        path = "~" + path[len(HOME):]
    return path


def abbreviatePath(path: str, style: PathDisplayStyle = PathDisplayStyle.FULL_PATHS) -> str:
    if style == PathDisplayStyle.ABBREVIATE_DIRECTORIES:
        splitLong = path.split('/')
        for i in range(len(splitLong) - 1):
            if splitLong[i][0] == '.':
                splitLong[i] = splitLong[i][:2]
            else:
                splitLong[i] = splitLong[i][0]
        return '/'.join(splitLong)
    elif style == PathDisplayStyle.SHOW_FILENAME_ONLY:
        return path.rsplit('/', 1)[-1]
    else:
        return path


