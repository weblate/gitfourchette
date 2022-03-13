VERBOSE_TAGS = {"nav", "status", "benchmark"}


def info(tag, *args):
    if tag in VERBOSE_TAGS:
        return
    print(F"[{tag}]", *args)


def warning(tag, *args):
    print(F"!WARNING! [{tag}]", *args)


