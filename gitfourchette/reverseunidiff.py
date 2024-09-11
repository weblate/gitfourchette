import re


def reverseUnidiff(original: str):
    lines = original.splitlines(keepends=True)
    newPatch = ""
    swapLine = ""

    for lineNum, ol in enumerate(lines, start=1):
        def check(condition):
            if not condition:  # pragma: no cover
                raise ValueError(f"Cannot reverse line {lineNum} in this patch.")  # noqa: B023

        if ol.startswith("diff "):
            p = r"^(diff( --git)?) a/(.+) b/(.+)"
            r = r"\1 a/\4 b/\3"
            newStr, numSubs = re.subn(p, r, ol)
            check(numSubs == 1)
            newPatch += newStr

        elif ol.startswith("index "):
            p = r"^index ([0-9a-fA-F]+)\.\.([0-9a-fA-F]+)"
            r = r"index \2..\1"
            newStr, numSubs = re.subn(p, r, ol)
            check(numSubs == 1)
            newPatch += newStr

        elif ol.startswith("--- a/"):
            check(not swapLine)
            swapLine = "+++ b/" + ol.removeprefix("--- a/")

        elif ol.startswith("+++ b/"):
            check(swapLine.startswith("+++ "))
            newPatch += "--- a/" + ol.removeprefix("+++ b/")
            newPatch += swapLine
            swapLine = ""

        elif ol.startswith("--- /dev/null"):
            check(not swapLine)
            swapLine = "+++ /dev/null\n"

        elif ol.startswith("+++ /dev/null"):
            check(swapLine.startswith("+++ "))
            newPatch += "--- /dev/null\n"
            newPatch += swapLine
            swapLine = ""

        elif ol.startswith("rename from "):
            check(not swapLine)
            swapLine = "rename to " + ol.removeprefix("rename from ")

        elif ol.startswith("rename to "):
            check(swapLine.startswith("rename to "))
            newPatch += "rename from " + ol.removeprefix("rename to ")
            newPatch += swapLine
            swapLine = ""

        elif ol.startswith("old mode "):
            check(not swapLine)
            swapLine = "new mode " + ol.removeprefix("old mode ")

        elif ol.startswith("new mode "):
            check(swapLine.startswith("new mode "))
            newPatch += "old mode " + ol.removeprefix("new mode ")
            newPatch += swapLine
            swapLine = ""

        elif ol.startswith("new file mode "):
            newPatch += "deleted file mode " + ol.removeprefix("new file mode ")

        elif ol.startswith("deleted file mode "):
            newPatch += "new file mode " + ol.removeprefix("deleted file mode ")

        elif ol.startswith("@@ "):
            p = r"^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@"
            r = r"@@ -\2 +\1 @@"
            newStr, numSubs = re.subn(p, r, ol)
            check(numSubs == 1)
            newPatch += newStr

        elif ol.startswith((" ", "\\")):  # context or "\No newline at end of file"
            newPatch += ol

        elif ol.startswith("+"):
            newPatch += "-" + ol[1:]

        elif ol.startswith("-"):
            newPatch += "+" + ol[1:]

        elif ol.startswith("similarity index "):
            newPatch += ol

        else:
            raise NotImplementedError(f"Unsupported prefix on line {lineNum}")

    if swapLine:
        raise ValueError("Incomplete patch")

    return newPatch


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    with open(path, 'rt', encoding='utf-8') as f:
        text = f.read()
    rev = reverseUnidiff(text)
    print(rev)
