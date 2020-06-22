from zlib import crc32


class Lanes:
    FORK_UP = 1
    FORK_DOWN = 2
    STRAIGHT = 4

    def __init__(self, withChecksum=False):
        self.lanes = []
        self.draw = []
        self.withChecksum = withChecksum
        self.check = 0

    def step(self, commit, parents):
        lanes = self.lanes

        def findFreeLane(startAt=0) -> int:
            try:
                return lanes.index(None, startAt)
            except ValueError:
                # all lanes taken: create one on the right
                free = len(lanes)
                lanes.append(None)
                paint.append(0)
                return free

        # start with all-straight lines
        # this is faster than starting with nothing and then adding straight lines
        paint = [Lanes.STRAIGHT] * len(lanes)

        # look up my lane.
        # the main lane for this commit is the leftmost lane reserved for it
        try:
            myLane = lanes.index(commit)
        except ValueError:
            # this commit is the tip of a branch
            myLane = findFreeLane()

        # comb through lanes and update draw data
        # (this is where the bulk of the time is spent in this function)
        for i, lane in enumerate(lanes):
            if lane is None:
                paint[i] = 0
            elif lane == commit:
                # tie up loose ends
                paint[i] = Lanes.FORK_UP
                lanes[i] = None  # free up lane

        # hand over my main lane to my first parent
        if len(parents) > 0:
            lanes[myLane] = parents[0]
            paint[myLane] |= Lanes.FORK_DOWN

        # add new branches for my other parents
        freeLane = 0
        for parent in parents[1:]:
            # find a free lane or create one if none is available
            freeLane = findFreeLane(freeLane)
            # fill it in
            lanes[freeLane] = parent
            paint[freeLane] |= Lanes.FORK_DOWN

        # compact free lanes on the right
        while len(lanes) > 0 and lanes[-1] is None:
            del lanes[-1]

        if self.withChecksum:
            self.updateChecksum(paint)

        return myLane, paint

    def updateChecksum(self, result):
        self.check = crc32(len(result).to_bytes(4, 'little'), self.check)
        for r in result:
            self.check = crc32(r.to_bytes(1, 'little'), self.check)
