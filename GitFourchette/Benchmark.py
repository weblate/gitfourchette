import timeit


class Benchmark:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.start = timeit.default_timer()

    def __exit__(self, exc_type, exc_value, traceback):
        tt = timeit.default_timer() - self.start
        print(F'Benchmark: {self.name}: {int(tt*1000)} ms')

