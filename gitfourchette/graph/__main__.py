if __name__ == '__main__':
    from gitfourchette.graph import *
    from argparse import ArgumentParser

    parser = ArgumentParser(description="GitFourchette ASCII graph tool")
    parser.add_argument("definition", help="Graph definition (e.g.: \"u:z i:b m:a,b a:z b-c-z\")", nargs="+")
    parser.add_argument("-t", "--tips", nargs="*", default=[])
    parser.add_argument("-x", "--hide", nargs="*", default=[])
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    definition = " ".join(args.definition)
    sequence, parentMap, heads = GraphDiagram.parseDefinition(definition)
    graph = Graph()
    graph.generateFullSequence(sequence, parentMap)

    hiddenCommits = set()
    if args.hide:
        hide = args.hide
        tips = args.tips or heads
        assert all(c in sequence for c in hide), "one of the given hidden commits isn't in the graph"
        assert all(c in sequence for c in tips), "one of the given tip commits isn't in the graph"
        hiddenTrickle = GraphTrickle.initForHiddenCommits(tips, hide)
        for commit in sequence:
            hiddenTrickle.newCommit(commit, parentMap[commit], hiddenCommits)

    if args.verbose:
        print("Hidden commits:", hiddenCommits)

    diagram = GraphDiagram.diagram(graph, hiddenCommits=hiddenCommits, verbose=args.verbose)
    print(diagram)
