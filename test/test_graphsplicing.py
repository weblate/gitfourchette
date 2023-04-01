from gitfourchette.graph import *
import pytest


SCENARIOS = {
    "one branch, one new commit": (
        "a,b b,c c,d d,e e",
        "n,a a,b b,c c,d d,e e"
    ),

    "one new commit": (
        "a,b b,e c,d d,e e,f f,g g",
        "n,a a,b b,e c,d d,e e,f f,g g"
    ),

    "several new commits": (
        "a,b b,e c,d d,e e,f f,g g",
        "m,n n,a o,e,a a,b b,e c,d d,e e,f f,g g"
    ),

    "change order of branches": (
        "a,b b,e c,d d,e e,f f,g g",
        "c,d d,e a,b b,e e,f f,g g"
    ),

    "delete top commit": (
        "x,a a,b b,e c,d d,e e,f f,g g",
        "a,b b,e c,d d,e e,f f,g g"
    ),

    "amend top commit": (
        "x,a a,b b,e c,d d,e e,f f,g g",
        "y,a a,b b,e c,d d,e e,f f,g g"
    ),

    "amend non-top commit": (
        "x,a a,b b,e c,d d,e e,f f,g g",
        "x,a a,b b,e y,d d,e e,f f,g g"
    ),

    "identical with 1 head": (
        "a,b b,c c,d d",
        "a,b b,c c,d d"
    ),

    "identical with 2 heads": (
        "a,b b,e c,d d,e e,f f,g g",
        "a,b b,e c,d d,e e,f f,g g"
    ),

    "lone commit appears at top": (
        "a,b b,c c,d d",
        "x a,b b,c c,d d",
    ),

    "lone commit appears in middle": (
        "a,b b,c c,d d",
        "a,b b,c x c,d d",
    ),

    "lone commit appears at bottom": (
        "a,b b,c c,d d",
        "a,b b,c c,d d x",
    ),

    "octopus": (
        "a,b b,c,d,e,f c,p d,q,f e,r f,s s,z r,z p,z q,z z",
        "a,b b,c,d,e,f c,p d,q,f e,r f,s s,z r,z p,z q,z z",
    ),

    "new commit appears at top; unchanged branches don't need to be reviewed": (
        "a,b b,c c,d d,e e,q f,g g,h h,i t,u i,r u,v v,s q,r r,s s x,y y,z z",
        "n a,b b,c c,d d,e e,q f,g g,h h,i t,u i,r u,v v,s q,r r,s s x,y y,z z",
    ),

    "neverending line": (
        "a,b b,c c",
        "x,z a,b b,c c"
    ),

    "new commits appear not at top": (
        "a,b b,c c,d d,e e,f f,g g",
        "a,b b,c c,d d,e x,y y,z z,e e,f f,g g",
    ),

    "commits disappear not at top": (
        "a,b b,c c,d d,e x,y y,z z,e e,f f,g g",
        "a,b b,c c,d d,e z,e e,f f,g g",
    ),

    "commits disappear at top": (
        "a,b b,c c,d d,e x,y y,z z,e e,f f,g g",
        "b,c c,d d,e x,y y,z z,e e,f f,g g",
    ),

    "branch disappears": (
        "a,b b,c p,q q,r r,c c,d d",
        "a,b b,c c,d d",
    ),

    "0 to 0": (
        "",
        "",
    ),

    "0 to 1": (
        "",
        "a"
    ),

    "0 to 2": (
        "",
        "a,b b"
    ),
 
    "1 to 2": (
        "b",
        "a,b b",
    ),

    "1 to 0": (
        "a",
        ""
    ),

    "many to 0": (
        "m,n n,a o,e,a a,b b,e c,d d,e e,f f,g g",
        "",
    ),

    "0 to many": (
        "",
        "m,n n,a o,e,a a,b b,e c,d d,e e,f f,g g",
    ),

    "completely different, newer is shorter": (
        "a,b b,c c,d d,e e,f f",
        "p,q q,r r",
    ),

    "completely different, newer is longer": (
        "p,q q,r r",
        "a,b b,c c,d d,e e,f f",
    ),

    "completely different, newer is longer, unclosed link when older depleted": (
        "p,q q,r r",
        "a,b,f b,c c,d d,e e,f f",
    ),

    "messy junctions": (
        "a,b b,c k,l c,c',l c',d l,e d,e e,f f",
        "a,b b,c k,l c,c',l p,q q,r,l r,c' c',d l,e d,e e,f f",
    ),

    "super messy junctions - shifted rows + existing junctions before & after equilibrium + 1 new junction": (
        "a,b b,c k,l c,c',l c',m m,n n,o o,d,l l,e d,e e,f f",
        "x,y y,z z,a a,b b,c k,l c,c',l p,q q,r,l r,c' c',m m,n n,o o,d,l l,e d,e e,f f",
    ),

    "super messy junctions reversed": (
        "x,y y,z z,a a,b b,c k,l c,c',l p,q q,r,l r,c' c',m m,n n,o o,d,l l,e d,e e,f f",
        "a,b b,c k,l c,c',l c',m m,n n,o o,d,l l,e d,e e,f f",
    ),

    "stash at top": (
        "a,b b,c c",
        "s1,a,s2 s2,a a,b b,c c"
    ),
}


def loadAncestryDefinition(text):
    sequence = []
    parentsOf = {}
    seen = set()
    heads = set()
    for line in text:
        line = line.strip()
        if not line:
            continue
        split = line.strip().split(",")
        commit = split[0]
        if commit in parentsOf:
            print("WARNING!!!!!! Commit hash appears twice in sequence:", commit)
        sequence.append(commit)
        parentsOf[commit] = split[1:]
        if commit not in seen:
            heads.add(commit)
        seen.update(parentsOf[commit])
    return sequence, parentsOf, heads


def verifyKeyframes(g: Graph):
    playback = g.startPlayback(0)

    for row, keyframe in zip(g.keyframeRows, g.keyframes):
        playback.advanceToCommit(keyframe.commit)

        frame1 = playback.copyCleanFrame()
        frame2 = keyframe.copyCleanFrame()

        assert frame1 == frame2, F"Keyframe at row {row} doesn't reflect reality"


@pytest.mark.parametrize('scenarioKey', SCENARIOS.keys())
def testGraphSplicing(scenarioKey):
    textGraph1, textGraph2 = SCENARIOS[scenarioKey]
    sequence1, parentsOf1, heads1 = loadAncestryDefinition(textGraph1.split(' '))
    sequence2, parentsOf2, heads2 = loadAncestryDefinition(textGraph2.split(' '))

    g = Graph()
    g.generateFullSequence(sequence1, parentsOf1)

    print(F"Graph before --------- (heads: {heads1})")
    print(g.textDiagram())
    print("Keyframes BEFORE REFRESH:", g.keyframeRows)
    print("Num arcs total BEFORE REFRESH:", g.startArc.getNumberOfArcsFromHere())

    # verify that all keyframes are correct
    verifyKeyframes(g)

    # modify top of history
    splicer = g.startSplicing(heads1, heads2)
    for commit2 in sequence2:
        splicer.spliceNewCommit(commit2, parentsOf2[commit2], commit2 in sequence1)
        if not splicer.keepGoing:
            print("Equilibrium found at:", commit2)
            break
    splicer.finish()

    for trashedCommit in (splicer.oldCommitsSeen - splicer.newCommitsSeen):
        assert trashedCommit not in sequence2, F"commit '{trashedCommit}' erroneously trashed"

    print(F"Graph after --------- (heads: {heads2})")
    print(g.textDiagram())
    print("Keyframes AFTER REFRESH:", g.keyframeRows)
    print("Num arcs total AFTER REFRESH:", g.startArc.getNumberOfArcsFromHere())

    # verify that the splicing was correct
    verification = Graph()
    verification.generateFullSequence(sequence2, parentsOf2)
    assert g.textDiagram() == verification.textDiagram()

    # verify that all keyframes are correct
    verifyKeyframes(g)
