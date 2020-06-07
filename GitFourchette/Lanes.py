class Lanes:
    FORK_UP = 1
    FORK_DOWN = 2
    STRAIGHT = 4

    def __init__(self):
        self.lanes = []
        self.peakLanes = 0

    def step(self, commit, parents):
        if 0 == len(self.lanes):  # first call: put first commit in first lane
            self.lanes.append(commit)

        extraParentLanes = max(0, len(parents) - 1)

        result = [0] * (len(self.lanes) + extraParentLanes)

        myLane = self.lanes.index(commit)

        for i, lane in enumerate(self.lanes):
            if lane == commit:
                result[i] |= Lanes.FORK_UP
                self.lanes[i] = None
            elif lane is not None:
                result[i] |= Lanes.STRAIGHT

        # continue straight line
        if len(parents) > 0:
            self.lanes[myLane] = parents[0]
            result[myLane] |= Lanes.FORK_DOWN

        # compact free lanes on the right
        while len(self.lanes) > 0 and self.lanes[-1] is None:
            self.lanes.pop()

        # add new branches outwards
        for parent in parents[1:]:
            result[len(self.lanes)] |= Lanes.FORK_DOWN
            self.lanes.append(parent)

        return myLane, result

