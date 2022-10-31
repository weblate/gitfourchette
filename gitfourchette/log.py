class Logger:
    def __init__(self):
        self.verboseTags = {"nav", "status", "benchmark", "workqueue"}
        self.verbosity = 1

    def info(self, tag, *args):
        if self.verbosity == 0 or (self.verbosity == 1 and tag in self.verboseTags):
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
