import pytest

from gitfourchette.repostate import HiddenCommitSolver


class MockCommit:
    def __init__(self, name, parents=[]):
        self.oid = name
        self.parents = parents


@pytest.fixture
def hideCommitTestSequence():
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


def testHideSideBranch(hideCommitTestSequence):
    solver = HiddenCommitSolver(["b1"])

    for commit in hideCommitTestSequence:
        solver.feed(commit)

    print(solver._nextHidden)
    assert solver.done
    assert solver.hiddenCommits == {"b1", "b2"}


def testHideMainBranch(hideCommitTestSequence):
    solver = HiddenCommitSolver(["a1"])

    for commit in hideCommitTestSequence:
        solver.feed(commit)

    assert solver.hiddenCommits == {"a1", "a2"}
