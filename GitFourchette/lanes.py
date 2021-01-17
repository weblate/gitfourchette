import sys
import collections
import bisect
from dataclasses import dataclass

# - Using shortened int hashes instead of full hash strings doesn't seem to affect memory use much.
# - With a keyframe/replay approach (take snapshot every 100 steps, replay 99 other steps from keyframe),
#   we might not even need to keep 'self.lanes' around.

import settings


@dataclass  # gives us an equality operator as required by partial repo refresh
class LaneFrame:
    myLane: int
    lanesAbove: list[str]
    lanesBelow: list[str]


class LaneGenerator:
    def __init__(self):
        self.lanes = []
        self.laneLookup = collections.defaultdict(list)
        self.check = 0
        self.freeLanes = []
        self.pCopy = []
        self.nBytes = 0
        self.nLanesPeak = 0
        self.nLanesTotal = 0
        self.nLanesVacant = 0
        self.MAX_LANES = settings.prefs.graph_maxLanes
        self.FORCE_NEW_LANES_RIGHTMOST = settings.prefs.graph_newLanesAlwaysRightmost

    def step(self, commit, parents) -> LaneFrame:
        lanes = self.lanes
        freeLanes = self.freeLanes

        def findFreeLane() -> int:
            if not self.FORCE_NEW_LANES_RIGHTMOST and freeLanes:
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

        # add new branches to the right for my other parents that don't have a reserved lane already
        for parent in parents[1:]:
            if self.laneLookup[parent]:  # a lane is already reserved for this parent
                continue
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

        pCopy = self.pCopy
        nCopy = lanes[:self.MAX_LANES].copy()
        self.pCopy = nCopy

        # Some stats
        self.nLanesPeak = max(len(lanes), self.nLanesPeak)
        self.nLanesTotal += len(lanes)
        self.nLanesVacant += len(self.freeLanes)
        self.nBytes += sys.getsizeof(lanes)

        frame = LaneFrame(myLane, pCopy, nCopy)
        return frame
