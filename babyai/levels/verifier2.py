"""
Baby language grammar:
Sent -> Sent1 | Sent1 then Sent1 | Sent1 after you Sent1
Sent1 -> Clause | Clause and Clause
Clause -> go to Descr | open DescrDoor | put DescrNotDoor next to Descr
DescrDoor -> the Color door LocSpec
DescrBall -> the Color ball LocSpec
DescrBox -> the Color box LocSpec
DescrKey -> the Color key LocSpec
DescrNotDoor -> DescrBall | DescrBox | DescrKey
LocSpec -> “” | on your left | on your right | in front of you | behind you
Color -> red | purple | green | blue | yellow | orange
"""

import numpy as np
from enum import Enum
from gym_minigrid.minigrid import COLOR_NAMES, DIR_TO_VEC

# Object types we are allowed to describe in language
OBJ_TYPES = ['box', 'ball', 'key', 'door']

# Locations are all relative to the agent's starting position
LOC_NAMES = ['left', 'right', 'front', 'behind']


def dot_product(v1, v2):
    """
    Compute the dot product of the vectors v1 and v2.
    """

    return sum([i*j for i, j in zip(v1, v2)])


class ObjDesc:
    """
    Description of an object
    """

    def __init__(self, type, color=None, loc=None):
        if type is 'locked_door':
            type = 'door'

        assert type in OBJ_TYPES
        assert color in [None, *COLOR_NAMES]
        assert loc in [None, *LOC_NAMES]

        self.color = color
        self.type = type
        self.loc = loc

        # Set of objects possibly matching the description
        self.obj_set = []

    def surface(self, env):
        self.find_matching_objs(env)
        assert len(self.obj_set) > 0

        s = str(self.type)

        if self.color:
            s = self.color + ' ' + s

        if self.loc:
            if self.loc == 'front':
                s = s + ' in front of you'
            elif self.loc == 'behind':
                s = s + ' behind you'
            else:
                s = s + ' on your ' + self.loc

        if len(self.obj_set) > 1:
            s = 'a ' + s
        else:
            s = 'the ' + s

        return s

    def find_matching_objs(self, env):
        """
        Find the set of objects matching the description
        """

        self.obj_set = []
        self.obj_poss = []

        for i in range(env.grid.width):
            for j in range(env.grid.height):
                cell = env.grid.get(i, j)
                if cell == None:
                    continue

                if cell.type == "locked_door":
                    type = "door"
                else:
                    type = cell.type

                # Check if object's type matches description
                if self.type != None and type != self.type:
                    continue

                # Check if object's color matches description
                if self.color != None and cell.color != self.color:
                    continue

                # Check if object's position matches description
                if self.loc in ["left", "right", "front", "behind"]:
                    # Direction from the agent to the object
                    v = (i-env.start_pos[0], j-env.start_pos[1])

                    # (d1, d2) is an oriented orthonormal basis
                    d1 = DIR_TO_VEC[env.start_dir]
                    d2 = (-d1[1], d1[0])

                    # Check if object's position matches with location
                    pos_matches = {
                        "left": dot_product(v, d2) < 0,
                        "right": dot_product(v, d2) > 0,
                        "front": dot_product(v, d1) > 0,
                        "behind": dot_product(v, d1) < 0
                    }

                    if not(pos_matches[self.loc]):
                        continue

                self.obj_set.append(cell)
                self.obj_poss.append((i, j))

        return self.obj_set, self.obj_poss


class Instr:
    """
    Base class for all instructions in the baby language
    """

    def __init__(self):
        self.env = None

    def surface(self, env):
        raise NotImplementedError

    def reset_verifier(self, env):
        self.env = env

    def verify(self, action):
        raise NotImplementedError


class Action(Instr):
    pass


class Open(Action):
    def __init__(self, obj_desc):
        assert obj_desc.type is 'door'
        self.desc = obj_desc

    def surface(self, env):
        return 'open ' + self.desc.surface(env)

    def reset_verifier(self, env):
        super().reset_verifier(env)

        # Identify set of possible matching objects in the environment
        self.desc.find_matching_objs(env)

    def verify(self, action):
        for door in self.desc.obj_set:
            if door.is_open:
                return 'success'

        return 'continue'


class GoTo(Action):
    def __init__(self, obj_desc):
        self.desc = obj_desc

    def surface(self, env):
        return 'go to ' + self.desc.surface(env)

    def reset_verifier(self, env):
        super().reset_verifier(env)

        # Identify set of possible matching objects in the environment
        self.desc.find_matching_objs(env)

    def verify(self, action):
        # For each object position
        for pos in self.desc.obj_poss:
            # If the agent is next to (and facing) the object
            if np.array_equal(pos, self.env.front_pos):
                return 'success'

        return 'continue'


class Pickup(Action):
    def __init__(self, obj_desc):
        assert obj_desc.type is not 'door'
        self.desc = obj_desc

    def surface(self, env):
        return 'pick up ' + self.desc.surface(env)

    def reset_verifier(self, env):
        super().reset_verifier(env)

        # Identify set of possible matching objects in the environment
        self.desc.find_matching_objs(env)

    def verify(self, action):
        for obj in self.desc.obj_set:
            if self.env.carrying is obj:
                return 'success'

        return 'continue'


class PutNext(Action):
    def __init__(self, obj_move, obj_fixed):
        assert obj_move.type is not 'door'
        self.desc_move = obj_move
        self.desc_fixed = obj_fixed


class Then(Instr):
    """
    Sequence two instructions in order:
    eg: go to the red door then pick up the blue ball
    """

    def __init__(self, instr_a, instr_b):
        assert isinstance(instr_a, Action) or isinstance(instr_a, Both)
        assert isinstance(instr_b, Action) or isinstance(instr_b, Both)
        self.instr_a = instr_a
        self.instr_b = instr_b

    def surface(self, env):
        return self.instr_a.surface(env) + ' then ' + self.instr_b.surface(env)

    def reset_verifier(self, env):
        super().reset_verifier(env)
        self.instr_a.reset_verifier(env)
        self.instr_b.reset_verifier(env)

    def verify(self, action):
        # TODO: abort early if incorrect sequence

        # TODO
        return 'continue'


class After(Instr):
    """
    Sequence two instructions in reverse order:
    eg: go to the red door after you pick up the blue ball
    """

    def __init__(self, instr_a, instr_b):
        assert isinstance(instr_a, Action) or isinstance(instr_a, Both)
        assert isinstance(instr_b, Action) or isinstance(instr_b, Both)
        self.instr_a = instr_a
        self.instr_b = instr_b

    def surface(self, env):
        return self.instr_a.surface(env) + ' then ' + self.instr_b.surface(env)


class Both(Instr):
    """
    Conjunction of two actions, both can be completed in any other
    eg: go to the red door and pick up the blue ball
    """

    def __init__(self):
        pass