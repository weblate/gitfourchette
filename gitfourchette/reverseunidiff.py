from hashlib import new
import re


def reverseUnidiff(original: str):
    lines = original.splitlines(keepends=True)

    newPatch = ""

    pendingLineSwap = ""

    for lineNum, ol in enumerate(lines, start=1):
        if ol.startswith("diff "):
            p = r"^(diff( --git)?) a\/(.+) b\/(.+)"
            r = r"\1 a/\4 b/\3"
            newStr, numSubs = re.subn(p, r, ol)
            if numSubs != 1:
                raise ValueError("Cannot reverse this patch.")
            newPatch += newStr

        elif ol.startswith("index "):
            p = r"^index ([0-9a-fA-F]+)\.\.([0-9a-fA-F]+)"
            r = r"index \2..\1"
            newStr, numSubs = re.subn(p, r, ol)
            if numSubs != 1:
                raise ValueError("Cannot reverse this patch.")
            newPatch += newStr

        elif ol.startswith("--- a/"):
            if pendingLineSwap:
                raise ValueError("Cannot reverse this patch.")
            pendingLineSwap = "+++ b/" + ol.removeprefix("--- a/")

        elif ol.startswith("+++ b/"):
            if not pendingLineSwap:
                raise ValueError("Cannot reverse this patch.")
            newPatch += "--- a/" + ol.removeprefix("+++ b/")
            newPatch += pendingLineSwap
            pendingLineSwap = ""

        elif ol.startswith("old mode"):
            if pendingLineSwap:
                raise ValueError("Cannot reverse this patch.")
            pendingLineSwap = "new " + ol.removeprefix("old ")

        elif ol.startswith("new mode"):
            if not pendingLineSwap:
                raise ValueError("Cannot reverse this patch.")
            newPatch += "old " + ol.removeprefix("new ")
            newPatch += pendingLineSwap
            pendingLineSwap = ""

        elif ol.startswith("@@ "):
            p = r"^@@ \-(\d+,\d+) \+(\d+,\d+) @@"
            r = r"@@ -\2 +\1 @@"
            newStr, numSubs = re.subn(p, r, ol)
            assert numSubs == 1
            newPatch += newStr

        elif ol.startswith(" "):
            newPatch += ol
        elif ol.startswith("+"):
            newPatch += "-" + ol[1:]
        elif ol.startswith("-"):
            newPatch += "+" + ol[1:]
        else:
            raise ValueError("Unsupported line prefix for reversing")

    return newPatch

if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    with open(path, "rt") as f:
        text = f.read()
    rev = reverseUnidiff(text)
    print(rev)