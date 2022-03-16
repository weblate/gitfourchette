VERBOSE_TAGS = {"nav", "status", "benchmark"}
VERBOSITY = 1


def info(tag, *args):
    if VERBOSITY == 0 or (VERBOSITY == 1 and tag in VERBOSE_TAGS):
        return
    print(F"[{tag}]", *args)


def warning(tag, *args):
    print(F"!WARNING! [{tag}]", *args)


