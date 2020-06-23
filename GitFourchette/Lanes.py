from zlib import crc32

import collections
import bisect


class Lanes:
    FORK_UP = 1
    FORK_DOWN = 2
    STRAIGHT = 4

    def __init__(self, withChecksum=False):
        self.lanes = []
        self.laneLookup = collections.defaultdict(list)
        self.withChecksum = withChecksum
        self.check = 0
        self.freeLanes = []
        self.pCopy = []

    def step(self, commit, parents):
        lanes = self.lanes
        freeLanes = self.freeLanes

        def findFreeLane() -> int:
            if freeLanes:
                return freeLanes.pop(0)
            else:
                # all lanes taken: create one on the right
                free = len(lanes)
                lanes.append(None)
                return free

        hasParents = len(parents) != 0

        # comb through lanes and update draw data
        allMyLanes = self.laneLookup.get(commit)
        if allMyLanes is not None:
            myLane = min(allMyLanes)  # slightly faster than looking for the min in the loop
            for i in allMyLanes:
                # tie up loose ends
                lanes[i] = None  # free up lane
                if i != myLane or not hasParents:
                    bisect.insort(freeLanes, i)
            del self.laneLookup[commit]
        else:
            # this commit is the tip of a branch
            myLane = findFreeLane()

        # hand over my main lane to my first parent
        if hasParents:
            lanes[myLane] = parents[0]
            self.laneLookup[parents[0]].append(myLane)

        # add new branches for my other parents
        for parent in parents[1:]:
            # find a free lane or create one if none is available
            freeLane = findFreeLane()
            # fill it in
            lanes[freeLane] = parent
            self.laneLookup[parent].append(freeLane)

        # compact free lanes on the right
        while len(lanes) > 0 and lanes[-1] is None:
            assert freeLanes[-1] == len(lanes)-1
            freeLanes.pop()
            del lanes[-1]

        if self.withChecksum:
            pass #self.updateChecksum(paint)

        pCopy = self.pCopy
        nCopy = lanes[:32].copy()
        self.pCopy = nCopy
        return myLane, pCopy, nCopy

    def updateChecksum(self, result):
        self.check = crc32(len(result).to_bytes(4, 'little'), self.check)
        for r in result:
            self.check = crc32(r.to_bytes(1, 'little'), self.check)
