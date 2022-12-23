import pytest

from gitfourchette.hiddencommitsolver import HiddenCommitSolver


class MockCommit:
    def __init__(self, name, parents=[]):
        self.oid = name
        self.parents = parents


@pytest.fixture
def seq1():
    """

    a1
     |
    a2
     |
     |   b1
     |    |
     |   b2
     |  /
    a3
     |
    a4

    """

    a4 = MockCommit("a4", [])
    a3 = MockCommit("a3", [a4])
    a2 = MockCommit("a2", [a3])
    a1 = MockCommit("a1", [a2])

    b2 = MockCommit("b2", [a3])
    b1 = MockCommit("b1", [b2])

    seq = [a1, a2, b1, b2, a3, a4]
    return seq


@pytest.fixture
def seq2():
    """

    a1
     |
    a2
     |
     |   b1
     |    | \
     |    |  b2
     |    |  |
     |    |  b3
     |    |  |
    a3----/--/
     |
    a4

    """

    a4 = MockCommit("a4", [])
    a3 = MockCommit("a3", [a4])
    a2 = MockCommit("a2", [a3])
    a1 = MockCommit("a1", [a2])

    b3 = MockCommit("b3", [a3])
    b2 = MockCommit("b2", [b3])
    b1 = MockCommit("b1", [a3, b2])

    seq = [a1, a2, b1, b2, b3, a3, a4]
    return seq


def testHideSideBranch(seq1):
    solver = HiddenCommitSolver()
    solver.hideCommit("b1")
    solver.feedSequence(seq1)
    assert solver.done
    assert solver.hiddenCommits == {"b1", "b2"}


def testHideMainBranch(seq1):
    solver = HiddenCommitSolver()
    solver.hideCommit("a1")
    solver.feedSequence(seq1)
    assert solver.hiddenCommits == {"a1", "a2"}


def testDontHideBranchIfConnectedByShownCommit(seq2):
    solver = HiddenCommitSolver()
    solver.hideCommit("b2")
    solver.feedSequence(seq2)
    assert solver.done
    assert solver.hiddenCommits == set()


def testForceHideBranch(seq2):
    """ Simulates hiding an 'index on...' commit which is the parent of a stash """
    solver = HiddenCommitSolver()
    solver.hideCommit("b2", force=True)
    solver.feedSequence(seq2)
    assert solver.done
    assert solver.hiddenCommits == {"b2", "b3"}
