"""
Utility functions.
"""
from collections import UserDict
from collections.abc import Callable
from functools import cache as _cache
from functools import lru_cache as _lru_cache
from functools import wraps as _wraps
from types import NoneType
from typing import cast, overload, override


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


def cache[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """
    Typed wrapper around `functools.cache`.

    Unlike `functools.cache`, the returned
    function has the same signature as the
    cached function. The callable instead
    isn't constrained to something that
    takes hashables and lacks utilities to
    access cache attributes.
    """
    return cast("Callable[P, R]", _wraps(fn)(_cache(fn))) # type: ignore[reportInvalidCast]


@overload
def lru_cache[**P, R](
        maxsize: Callable[P, R],
        *,
        typed: bool = False,
) -> Callable[P, R]:
    ...


@overload
def lru_cache[**P, R](
        maxsize: int | None = 128,
        *,
        typed: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...


def lru_cache[**P, R](
        maxsize: Callable[P, R] | int | None = 128,
        *,
        typed: bool = False,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Typed wrapper around `functools.lru_cache`.

    Unlike `functools.lru_cache`, the returned
    function has the same signature as the cached
    function.  The callable instead isn't constrained
    to something that takes hashables and lacks
    utilities to access cache attributes.
    """
    if isinstance(maxsize, int | NoneType):
        def inner(fn: Callable[P, R]) -> Callable[P, R]:
            return cast("Callable[P, R]", _wraps(fn)(_lru_cache(maxsize, typed)(fn))) # type: ignore[reportInvalidCast]
        return inner
    return cast("Callable[P, R]", _wraps(maxsize)(_lru_cache(typed=typed)(maxsize))) # type: ignore[reportInvalidCast]


class LruDict[Kt, Vt](UserDict[Kt, Vt]):
    """
    Least Recently Used dictionary.

    By default stores the last 50 items.
    """

    max_size: int = 50

    @override
    def __setitem__(self, key: Kt, item: Vt) -> None:
        while len(self) > self.max_size:
            key = next(iter(self))
            del self[key]
        return super().__setitem__(key, item)
