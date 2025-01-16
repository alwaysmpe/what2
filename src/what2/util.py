"""
Utility functions.
"""


def clamp[T: int | float](lower: T, val: T, upper: T) -> T:
    """
    Clamp a number to a given range.

    Or more strictly return the middle number of the
    ordered triplet.

    :param lower:   The lower bound.
    :param val:     The value to clamp.
    :param upper:   The upper bound.
    :returns:       The clamped value.
    """
    return sorted((lower, val, upper))[1]
