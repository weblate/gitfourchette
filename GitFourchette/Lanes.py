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

        result = [0] * len(self.lanes)

        # cached index of the first free lane
        freeLane = len(self.lanes)

        myLane = self.lanes.index(commit)

        for i, lane in enumerate(self.lanes):
            if lane == commit:
                result[i] |= Lanes.FORK_UP
                self.lanes[i] = None
            elif lane is not None:
                result[i] |= Lanes.STRAIGHT
            # cache first free lane (re-test self.lanes[i] because we might have freed a lane above)
            if self.lanes[i] is None and i < freeLane:
                freeLane = i

        # continue straight line
        if len(parents) > 0:
            self.lanes[myLane] = parents[0]
            result[myLane] |= Lanes.FORK_DOWN

        # add new branches
        for parent in parents[1:]:
            # find a free lane
            try:
                freeLane = self.lanes.index(None, freeLane)
            except ValueError:
                # all lanes taken: add new lane
                freeLane = len(self.lanes)
                self.lanes.append(None)
                result.append(0)
            # fill it in
            self.lanes[freeLane] = parent
            result[freeLane] |= Lanes.FORK_DOWN

        # compact free lanes on the right
        while len(self.lanes) > 0 and self.lanes[-1] is None:
            del self.lanes[-1]

        return myLane, result

