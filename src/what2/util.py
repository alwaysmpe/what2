from  numbers import Real
from collections.abc import Set
from collections.abc import Hashable


def clamp[T: Real | float](lower: T, val: T, upper: T) -> T:
    return sorted((lower, val, upper))[1]
