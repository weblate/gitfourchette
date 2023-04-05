import pytest
from gitfourchette.graph import *
from .test_graphsplicer import parseAncestryOneLiner
from dataclasses import dataclass


@dataclass
class ChainMarkerFixture:
    graphName: str

    graphDef: str

    headsDef: str

    hiddenCommits: dict
    """ Map of hidden commit seeds to a list of all hidden commits,
    assuming the only "important" commits are listed out in graphDef.
    All unlisted commits are considered to be "visible". """

    localCommits: dict
    """ Map of local commit seeds to a list of all local commits.
    All unlisted commits are considered to be "foreign". """

    def generateGraph(self):
        sequence, parentMap, heads = parseAncestryOneLiner(self.graphDef)
        g = Graph()
        g.generateFullSequence(sequence, parentMap)
        assert set(self.headsDef.split()) == set(heads)
        return g

    def hiddenCommitsParametrizedArgs(self):
        return [(self.generateGraph(), self.headsDef.split(), k.split(), v.split()) for k, v in self.hiddenCommits.items()]

    def hiddenCommitsParametrizedNames(self):
        return [self.graphName + ": " + k for k in self.hiddenCommits]

    def localCommitsParametrizedArgs(self):
        return [(self.generateGraph(), k.split(), v.split()) for k, v in self.localCommits.items()]

    def localCommitsParametrizedNames(self):
        return [self.graphName + ": " + k for k in self.localCommits]


allFixtures = [
    # a1 ┯
    # b1 │ ┯
    # c1 │ │ ┯
    # a2 ┿─╯ │
    # c2 │   ┿
    # d1 │ ┯ │
    # a3 ┿ │ │
    #  f ┿─╯─╯
    #    ├─╮
    # f1 ┷ │
    # g1   ┷
    ChainMarkerFixture(
        graphName="typical",
        graphDef="a1,a2 b1,a2 c1,c2 a2,a3 c2,f d1,f a3,f f,f1,g1 f1 g1",
        headsDef="a1 b1 c1 d1",

        hiddenCommits={
            "": "",

            "a1": "a1",
            "b1": "b1",
            "c1": "c1 c2",
            "a2": "",  # don't hide anything because a1/b1 still visible
            "c2": "",  # don't hide anything because c1 still visible
            "d1": "d1",
            "a3": "",

            "a1 b1": "a1 b1 a2 a3",
            "b1 c1": "b1 c1 c2",
            "c1 d1": "c1 c2 d1",

            "a1 b1 a2": "a1 b1 a2 a3",
            "b1 c1 d1": "b1 c1 c2 d1",

            "a1 b1 c1": "a1 a2 b1 c1 c2 a3",
            "a1 b1 c1 d1": "a1 a2 b1 c1 c2 a3 d1 f f1 g1",
        },

        localCommits={
            "": "",

            "a1": "a1 a2 a3 f f1 g1",
            "a2": "a2 a3 f f1 g1",
            "a3": "a3 f f1 g1",
            "b1": "b1 a2 a3 f f1 g1",
            "c1": "c1 c2 f f1 g1",
            "c2": "c2 f f1 g1",
            "d1": "d1 f f1 g1",
            "f": "f f1 g1",

            "a1 b1": "a1 a2 a3 b1 f f1 g1",
            "a1 c1": "a1 a2 a3 c1 c2 f f1 g1",
            "a1 d1": "a1 a2 a3 d1 f f1 g1",

            "a1 b1 c1": "a1 a2 a3 b1 c1 c2 f f1 g1",

            "a1 b1 c1 d1": "a1 a2 a3 b1 c1 c2 d1 f f1 g1",
        },
    ),

    #  a ┯
    # sc │ ┯
    #    │ │─╮─╮
    # si │ │ ┿ │
    # su │ │ │ ┷
    #  b ┿─╯─╯
    #  c ┷
    ChainMarkerFixture(
        graphName="stash",
        graphDef="a,b sc,b,si,su si,b su b,c c",
        headsDef="a sc",

        hiddenCommits={
            "": "",
            "a": "a",
            "b": "",  # cannot be hidden because VIP commits depend on it
            "sc": "sc si su",
            "a sc": "a sc si su b c",
            "su": "su",
            "si": "si",
            "si su": "si su",
        },

        localCommits={
            "": "",
            "a": "a b c",
            "a b": "a b c",
            "sc": "sc si su b c",
            "a sc": "a sc si su b c",
        },
    ),

    # a ┯
    # b │ ┯
    # c ┿─╯  (intentionally incomplete)
    ChainMarkerFixture(
        graphName="incomplete",
        graphDef="a,c b,c c,missingparent",
        headsDef="a b",

        hiddenCommits={
            "": "",
            "a": "a",
            "b": "b",
            "c": "",
            "a b": "a b c",
            "a b c": "a b c",
        },

        localCommits={
            "": "",
            "a": "a c",
            "b": "b c",
            "c": "c",
            "a b": "a b c",
            "a b c": "a b c",
        },
    ),
]


@pytest.mark.parametrize(
    argnames=("graph", "heads", "seeds", "expected"),
    argvalues=itertools.chain.from_iterable(g.hiddenCommitsParametrizedArgs() for g in allFixtures),
    ids=itertools.chain.from_iterable(g.hiddenCommitsParametrizedNames() for g in allFixtures),
)
def testHiddenCommitMarks(graph, heads, seeds, expected):
    print("\n"+graph.textDiagram())
    print("Seed hidden commits:", seeds)
    print("Expected hidden commits:", expected)

    cm = GraphMarker(graph)

    # The order of the marking below is IMPORTANT

    # FIRST, mark HIDDEN NON-heads as FORCE-HIDDEN
    for c in set(seeds) - set(heads):
        print(f"Marking {c} as FORCE-HIDDEN")
        cm.mark(c, 0, recurse=False)

    # THEN, mark NON-HIDDEN heads as VISIBLE
    for c in set(heads) - set(seeds):
        print(f"Marking {c} as VISIBLE")
        cm.mark(c, 1)

    for c in graph.commitRows.keys():
        lookedUp = cm.lookup(c, -1)
        isVisible = lookedUp > 0
        print(f"Looking up {c} (supposed to be {'hidden' if c in expected else 'visible'}) resulted in {lookedUp}")
        assert isVisible == (c not in expected)
        print(c, "PASS", lookedUp)


@pytest.mark.parametrize(
    argnames=("graph", "seeds", "expected"),
    argvalues=itertools.chain.from_iterable(g.localCommitsParametrizedArgs() for g in allFixtures),
    ids=itertools.chain.from_iterable(g.localCommitsParametrizedNames() for g in allFixtures),
)
def testLocalCommitMarks(graph, seeds, expected):
    print("\n"+graph.textDiagram())
    print("Seed commits:", seeds)
    print("Expected commits:", expected)

    cm = GraphMarker(graph)

    for c in seeds:
        print(f"Marking {c} as LOCAL")
        cm.mark(c)

    for c in graph.commitRows.keys():
        lookedUp = cm.lookup(c)
        assert lookedUp == (c in expected), f"{c} should be marked {c in expected}, was marked {lookedUp}"
        print(c, "PASS", lookedUp)
