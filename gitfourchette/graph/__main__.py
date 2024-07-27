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
    sequence, heads = GraphDiagram.parseDefinition(definition)

    idSequence = [c.id for c in sequence]
    assert all(c in idSequence for c in args.hide), "one of the given hidden commits isn't in the graph"
    assert all(c in idSequence for c in args.tips), "one of the given tip commits isn't in the graph"

    builder = GraphBuildLoop(args.tips or heads, hiddenTips=args.hide).sendAll(sequence)

    if args.verbose:
        print("Hidden commits:", builder.hiddenCommits)

    diagram = GraphDiagram.diagram(builder.graph, hiddenCommits=builder.hiddenCommits, verbose=args.verbose)
    print(diagram)
