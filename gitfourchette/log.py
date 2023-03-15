import enum


class Logger:
    class Verbosity(enum.IntEnum):
        QUIET = 0
        NORMAL = 1
        BENCHMARK = 2
        VERBOSE = 3

    def __init__(self):
        self.verbosity = Logger.Verbosity.NORMAL

        self.excludeTags = {Logger.Verbosity.BENCHMARK: {"nav", "status", "repotaskrunner"},
                            Logger.Verbosity.NORMAL: {"nav", "status", "repotaskrunner", "benchmark"},
                            Logger.Verbosity.VERBOSE: {}}

    def info(self, tag, *args):
        if self.verbosity == Logger.Verbosity.QUIET or tag.lower() in self.excludeTags[self.verbosity]:
            return
        print(F"[{tag}]", *args)

    def warning(self, tag, *args):
        print(F"!WARNING! [{tag}]", *args)


logger = Logger()


def info(tag, *args):
    logger.info(tag, *args)


def warning(tag, *args):
    logger.warning(tag, *args)


def setVerbosity(verbosityLevel):
    logger.verbosity = verbosityLevel
