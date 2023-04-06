from gitfourchette import log
import os
import timeit

try:
    import psutil
except ModuleNotFoundError:
    log.info("benchmark", "psutil isn't available. Memory pressure estimates won't work.")
    psutil = None


def getRSS():
    if psutil:
        return psutil.Process(os.getpid()).memory_info().rss
    else:
        return 0


class Benchmark:
    """ Context manager that reports how long a piece of code takes to run. """

    nesting = []

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        Benchmark.nesting.append(self.name)
        self.rssAtStart = getRSS()
        self.start = timeit.default_timer()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        tt = timeit.default_timer() - self.start
        rss = getRSS()
        log.info("benchmark", F"{int(tt * 1000):6d}ms {(rss - self.rssAtStart) // 1024:6,d}K {'/'.join(Benchmark.nesting)}")
        Benchmark.nesting.pop()


def benchmark(func):
    """ Decorator that reports how long a function takes to run. """
    def wrapper(*args, **kwargs):
        with Benchmark(func.__name__):
            return func(*args, **kwargs)
    return wrapper
