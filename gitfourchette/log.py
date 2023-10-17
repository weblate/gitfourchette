import datetime
import enum
import sys


class Logger:
    class Verbosity(enum.IntEnum):
        QUIET = 0
        NORMAL = 1
        BENCHMARK = 2
        VERBOSE = 3

    def __init__(self):
        self.verbosity = Logger.Verbosity.NORMAL

        self.excludeTags = {Logger.Verbosity.BENCHMARK: {"nav", "status", "repotaskrunner"},
                            Logger.Verbosity.NORMAL: {"nav", "status", "repotaskrunner", "benchmark", "jump"},
                            Logger.Verbosity.VERBOSE: {}}

    @staticmethod
    def _print(file, tag, *args):
        timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%H:%M:%S")
        print(F"{timestamp} [{tag}]", *args, file=file)

    def info(self, tag, *args):
        if self.verbosity == Logger.Verbosity.QUIET or tag.lower() in self.excludeTags[self.verbosity]:
            return
        self._print(sys.stdout, tag, *args)

    def verbose(self, tag, *args):
        if self.verbosity != Logger.Verbosity.VERBOSE:
            return
        self._print(sys.stdout, tag, *args)

    def warning(self, tag, *args):
        self._print(sys.stderr, tag, *args)


logger = Logger()


def info(tag, *args):
    logger.info(tag, *args)


def verbose(tag, *args):
    logger.verbose(tag, *args)


def warning(tag, *args):
    logger.warning(tag, *args)


def setVerbosity(verbosityLevel):
    logger.verbosity = verbosityLevel
