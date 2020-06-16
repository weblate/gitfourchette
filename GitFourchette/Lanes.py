class Lanes:
    FORK_UP = 1
    FORK_DOWN = 2
    STRAIGHT = 4

    def __init__(self):
        self.lanes = []

    def _findFreeLane(self, result, startAt=0) -> int:
        try:
            return self.lanes.index(None, startAt)
        except ValueError:
            # all lanes taken: create one on the right
            free = len(self.lanes)
            self.lanes.append(None)
            result.append(0)
            return free

    def step(self, commit, parents):
        result = [0] * len(self.lanes)

        # the main lane for this commit is the leftmost lane reserved for it
        try:
            myLane = self.lanes.index(commit)
        except ValueError:
            # this commit is the tip of a branch
            myLane = self._findFreeLane(result)

        for i, lane in enumerate(self.lanes):
            if lane == commit:
                # tie up loose ends
                result[i] |= Lanes.FORK_UP
                self.lanes[i] = None
            elif lane is not None:
                # continue parallel lane that isn't mine
                result[i] |= Lanes.STRAIGHT

        # hand over my main lane to my first parent
        if len(parents) > 0:
            self.lanes[myLane] = parents[0]
            result[myLane] |= Lanes.FORK_DOWN

        # add new branches for my other parents
        freeLane = 0
        for parent in parents[1:]:
            # find a free lane or create one if none is available
            freeLane = self._findFreeLane(result, freeLane)
            # fill it in
            self.lanes[freeLane] = parent
            result[freeLane] |= Lanes.FORK_DOWN

        # compact free lanes on the right
        while len(self.lanes) > 0 and self.lanes[-1] is None:
            del self.lanes[-1]

        return myLane, result

