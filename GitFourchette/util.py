import re
from pathlib import Path


def fplural(fmt: str, n: int) -> str:
    out = fmt.replace("#", str(n))
    if n == 1:
        out = re.sub(r"\^\w+", "", out)
    else:
        out = out.replace("^", "")
    return out


def compactSystemPath(path: str) -> str:
    home = str(Path.home())
    if path.startswith(str(home)):
        path = "~" + path[len(home):]
    return path


def compactRepoPath(path: str) -> str:
    splitLong = path.split('/')
    for i in range(len(splitLong) - 1):
        if splitLong[i][0] == '.':
            splitLong[i] = splitLong[i][:2]
        else:
            splitLong[i] = splitLong[i][0]
    return '/'.join(splitLong)