"""
Implementation of `dbg` function.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
import enum
from functools import wraps
import inspect
from inspect import cleandoc
from pathlib import Path
from typing import Literal, NamedTuple, NotRequired, Self, TypedDict, Unpack, final, overload, override
import warnings

from what2.debug.notebook import is_notebook
from what2.util import LruDict, cache

try:
    from IPython.core.display import HTML as Html  # type: ignore[reportMissingModuleSource]
    from IPython.display import display  # type: ignore[reportMissingModuleSource]
    in_notebook = is_notebook()
except ImportError:
    if is_notebook():
        raise
    display = None
    Html = None
    in_notebook = False
from types import FrameType, TracebackType

type DebugImplT = Debug


class WarnKind(enum.StrEnum):
    """
    Enum indicating what warnings have been issued.
    """

    no_frame = (
        "Unable to inspect current stack frame, "
        "possibly running in optimized mode which "
        "is unsupported."
    )

    no_src = (
        "Unable to access call source code, "
        "possibly running in optimized mode which "
        "is unsupported."
    )

    parse_error = (
        "Error parsing call source, please raise "
        "an issue on github https://github.com/alwaysmpe/what2/issues"
    )


class ArgDescription(NamedTuple):
    """
    Description of a source argument to `dbg`.
    """

    is_const: bool
    arg_src: str


@final
@dataclass
class Debug(AbstractContextManager[DebugImplT]):
    """
    Implementation of `dbg` functionality.

    Tracks state, parses and caches source, splits
    polymorphic functionality into separate functions.
    """

    with_type: bool = False
    with_id: bool = False
    enabled: bool = True

    _ast_cache: LruDict[str, list[ArgDescription]] = field(default_factory=LruDict, init=False, repr=False, hash=False, compare=False)
    _warned_kinds: set[WarnKind] = field(default_factory=set, init=False, repr=False, hash=False, compare=False)

    def warn_frame_info(self, frame_depth: int, warn_kind: WarnKind) -> None:
        """
        Emit a warning (without duplication) at the caller site.

        :param frame_depth: The frame depth of the call to the parent function.
        :param warn_kind:   The warning to emit. Only emitted if it's new.
        """
        if warn_kind in self._warned_kinds:
            return
        else:
            self._warned_kinds.add(warn_kind)

        warnings.warn(
            message=warn_kind.value,
            category=RuntimeWarning,
            stacklevel=frame_depth + 1,
        )

    def simple_print(self, *args: *tuple[object, *tuple[object, ...]], **kwargs: Unpack[_DbgKwargs]) -> None:
        """
        Fallback print method.

        Comparable to default print.
        """
        with_id = kwargs.get("with_id", self.with_id)
        with_type = kwargs.get("with_type", self.with_type)

        for arg in args:
            if with_id:
                print(id(arg))
            if with_type:
                print(type(arg))
            print(arg, end="\n\n")

    def format_out(self, args: list[ArgDescription], arg_vals: tuple[object, *tuple[object, ...]], **kwargs: Unpack[_DbgKwargs]) -> None:
        """
        Format output paired with source argument description.
        """
        with_id = kwargs.get("with_id", self.with_id)
        with_type = kwargs.get("with_type", self.with_type)

        # TODO: what to do with consts?
        for (_is_const, arg_name), arg_value in zip(args, arg_vals, strict=False):
            arg_description = (
                arg_name,
                str(type(arg_value)) if with_type else None,
                f"id[{id(arg_value)}]" if with_id else None,
            )
            arg_description = f"{", ".join(filter(None, arg_description))}:"

            if in_notebook and display is not None and Html is not None:
                display(Html(f"<h5>{arg_description}</h5>"))
                display(arg_value)
            else:
                print(arg_description, arg_value, sep=" ", end="\n")
        print()

    @staticmethod
    def context(call_frame: FrameType) -> tuple[Path, int, str]:
        """
        Retrieve call frame context.
        """
        frame_info = inspect.getframeinfo(call_frame)
        line_number = frame_info.lineno

        parent_function = frame_info.function

        filepath = Path(frame_info.filename)
        return filepath, line_number, parent_function

    @classmethod
    @cache
    def default(cls) -> Self:
        """
        Retrieve the default quasi-singleton instance.
        """
        return cls()

    @classmethod
    def installed(cls) -> bool:
        """
        Whether the `dbg` function is installed in builtins.
        """
        return getattr(builtins, "dbg", None) is dbg

    @classmethod
    def install(cls) -> None:
        """
        Install the `dbg` function into builtins.

        This makes it globally available without import.
        """
        current = getattr(builtins, "dbg", None)

        if current is None:
            return setattr(builtins, "dbg", dbg)

        if current is not dbg:
            raise ValueError("different dbg instance already installed.")

    @classmethod
    def uninstall(cls) -> None:
        """
        Remove the `dbg` function from builtins.
        """
        current = getattr(builtins, "dbg", None)
        if current is dbg:
            return delattr(builtins, "dbg")
        if current is not None:
            raise ValueError("different dbg installed but asked to uninstall.")

    def dbg(self, *args: *tuple[object, *tuple[object, ...]], frame_depth: int = 1, **kwargs: Unpack[_DbgKwargs]) -> None:
        """
        Print the expression this function is called with and the value of that expression.

        Inspects the stack to retrieve the expression the function was called with.
        Also tries to format in a notebook environment.

        :param args: The values to be printed.
        :param frame_depth: If calling via proxy, set the stack
            depth to inspect for variable names.
        """
        if not kwargs.get("enabled", self.enabled):
            return None

        current_frame = inspect.currentframe()
        if current_frame is None:
            self.warn_frame_info(frame_depth=frame_depth, warn_kind=WarnKind.no_frame)
            return self.simple_print(*args, **kwargs)

        parent_frame_info = inspect.getouterframes(current_frame)[frame_depth]
        call_frame = parent_frame_info.frame

        frame_tb = inspect.getframeinfo(call_frame)
        fn_first_line = call_frame.f_code.co_firstlineno

        pos = frame_tb.positions
        if pos is None:
            self.warn_frame_info(frame_depth=frame_depth, warn_kind=WarnKind.no_src)
            return self.simple_print(*args, **kwargs)

        # line numbers are seemingly relative to
        # first line of function (but not documented
        # as such)
        first_line = pos.lineno
        if first_line is not None:
            first_line -= fn_first_line
        last_line = pos.end_lineno
        if last_line is not None:
            # closed range to half open range
            last_line += 1
            last_line -= fn_first_line

        call_code = inspect.getsource(call_frame).splitlines()[first_line: last_line]

        start_col = pos.col_offset
        end_col = pos.end_col_offset
        # Note: slice last line first incase it's only 1 line
        call_code[-1] = call_code[-1][:end_col]
        call_code[0] = call_code[0][start_col:]

        # cleandoc - by slicing the first line we're dedenting
        # that and that only, also dedent other lines for prettier
        # formatted code - not currently used
        call_src = cleandoc("\n".join(call_code))

        arg_names = self._ast_cache.get(call_src)
        if arg_names is None:
            try:
                arg_names = self.parse_args(call_src)
            except ValueError:
                self.warn_frame_info(frame_depth, WarnKind.parse_error)
                return self.simple_print(*args, **kwargs)

            self._ast_cache[call_src] = arg_names
        return self.format_out(arg_names, args, **kwargs)

    @staticmethod
    def parse_args(call_src: str) -> list[ArgDescription]:
        """
        Parse argument expressions from the source for a call to `dbg`.
        """
        call_lines = call_src.splitlines()
        call_mod_ast = ast.parse(call_src)
        call_ast = call_mod_ast.body[0]

        if not isinstance(call_ast, ast.Expr):
            raise ValueError
        call_ast = call_ast.value
        if not isinstance(call_ast, ast.Call):
            raise ValueError

        defs: list[ArgDescription] = []

        for arg in call_ast.args:

            lineno = arg.lineno
            end_lineno = arg.end_lineno
            col_offset = arg.col_offset
            end_col_offset = arg.end_col_offset

            if lineno:
                # linno/end_lineno 1 indexed, closed to half open
                lineno -= 1

            arg_lines = call_lines[lineno: end_lineno]
            arg_lines[-1] = arg_lines[-1][:end_col_offset]
            arg_lines[0] = arg_lines[0][col_offset:]
            arg_src = "\n".join(arg_lines)

            arg_desc = ArgDescription(arg_src=arg_src, is_const=isinstance(arg, ast.Constant))
            defs.append(arg_desc)

        return defs

    __stack: list[_DbgKwargs] = field(default_factory=list, init=False)

    @override
    def __enter__(self) -> Self:
        state = _DbgKwargs(
            enabled=self.enabled,
            with_type=self.with_type,
            with_id=self.with_id,
        )
        assert set(state) == _DbgKwargs.__optional_keys__ | _DbgKwargs.__required_keys__
        self.__stack.append(state)
        return self

    @override
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None, /) -> None:
        state = self.__stack.pop()
        for key, val in state.items():
            setattr(self, key, val)

    def __call__[**P, R](self, fn: Callable[P, R], **call_kwargs: Unpack[_EnableKwarg]) -> Callable[P, R]:
        """
        Directly call the instance as a decorator to a function.

        Can also be used via proxy to calls to `dbg`.
        """
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not call_kwargs.get("enabled", self.enabled):
                return fn(*args, **kwargs)

            print(f"{fn.__name__} called with args: {args} and kwargs: {kwargs}")
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                print(f"{fn.__name__}, exception: {e}")
                raise
            else:
                print(f"{fn.__name__}, result: {result}")
                return result

        return wrapper


class _EnableKwarg(TypedDict):
    enabled: NotRequired[bool]


class _DbgKwargs(_EnableKwarg):
    with_type: NotRequired[bool]
    with_id: NotRequired[bool]


class _CfgKwargs(_DbgKwargs):
    store: NotRequired[Literal[True]]


@final
@dataclass
class DebugProxy[CfgT: (_DbgKwargs, _EnableKwarg, None)](AbstractContextManager[None]):
    """
    Proxy calls to `Debug`.

    Mainly used for ambiguous call cases, eg
    decorator vs context manager.
    """

    impl: Debug
    kwargs: CfgT

    @override
    def __enter__(self: DebugProxy[_DbgKwargs] | DebugProxy[_EnableKwarg]) -> None:
        impl = self.impl
        kwargs = self.kwargs
        impl.__enter__()

        if "with_type" in kwargs:
            impl.with_type = kwargs["with_type"]
        if "with_id" in kwargs:
            impl.with_id = kwargs["with_id"]
        if "enabled" in kwargs:
            impl.enabled = kwargs["enabled"]

    def __call__[**P, R](self: DebugProxy[None] | DebugProxy[_EnableKwarg], fn: Callable[P, R], /) -> Callable[P, R]:
        """
        Proxy object call method.
        """
        if self.kwargs is None:
            return self.impl(fn)
        return self.impl(fn, **self.kwargs)

    @override
    def __exit__(self: DebugProxy[_DbgKwargs] | DebugProxy[_EnableKwarg], exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None, /) -> None:
        return self.impl.__exit__(exc_type, exc_value, traceback)


@overload
def dbg() -> DebugProxy[None]:
    ...


@overload
def dbg(
    *,
    enabled: bool,
) -> DebugProxy[_EnableKwarg]:
    ...


@overload
def dbg(
    *,
    with_type: bool,
    with_id: bool = ...,
    enabled: bool = ...,
) -> DebugProxy[_DbgKwargs]:
    ...


@overload
def dbg(
    *,
    with_type: bool = ...,
    with_id: bool,
    enabled: bool = ...,
) -> DebugProxy[_DbgKwargs]:
    ...


@overload
def dbg(
    *,
    with_type: bool,
    with_id: bool = ...,
    enabled: bool = ...,
    store: Literal[True],
) -> None:
    ...


@overload
def dbg(
    *,
    with_type: bool = ...,
    with_id: bool,
    enabled: bool = ...,
    store: Literal[True],
) -> None:
    ...


@overload
def dbg(
    *,
    with_type: bool = ...,
    with_id: bool = ...,
    enabled: bool,
    store: Literal[True],
) -> None:
    ...


@overload
def dbg(
    *args: *tuple[object, *tuple[object, ...]],
    with_type: bool = ...,
    with_id: bool = ...,
    enabled: bool = ...,
) -> None:
    ...


def dbg[**P, R](*args: *tuple[object, ...], **kwargs: Unpack[_CfgKwargs]) -> DebugProxy[_EnableKwarg] | DebugProxy[_DbgKwargs] | DebugProxy[None] | None:
    """
    Single function to configurably render arbitrary variable names and values.

    This function has several modes of use:

    * Call without arguments to use as a function decorator, or with `enabled` to explicitly enable/disable the decorator.
    * Call with option keywords and `store=True` to configure how a value is rendered.
    * Call as a context manager with option keywords without `store` to temoprarily configure within a context.
    * Call with positional arguments to print the names and values called with.

    Inspects the stack to retrieve the expression the function was called with.
    Also tries to format in a notebook environment.

    :param args: The values to be printed.
    :param with_type: Include the value type in output.
    :param with_id: Include the value id in output.
    :param enabled: Enable/disable all output
    :param store: If set, permanently store a option or if without temporarily
        apply within a context.

    Examples
    --------
    Will print the arguments and values its called with
    >>> from what2.debug import dbg
    >>> a = ["hello", "world"]
    >>> dbg(
    ...     a,
    ...     "foo",
    ... )
    a: ['hello', 'world']
    "foo": foo
    <BLANKLINE>

    This includes expressions:
    >>> from what2.debug import dbg
    >>> dbg(3+4)
    3+4: 7
    <BLANKLINE>

    When called without arguments, it returns
    a decorator that will report when a function
    is called and its arguments/returns/exceptions,
    which can be temporarily disabled within a scope:
    >>> from what2.debug import dbg
    >>> @dbg()
    ... def foo(arg: int) -> str:
    ...     return str(arg)
    >>> foo_ret = foo(4)
    foo called with args: (4,) and kwargs: {}
    foo, result: 4
    >>> with dbg(enabled=False):
    ...     foo_ret = foo(4)

    A specific decorator can be explicitly enabled
    or disabled, overriding context settings:
    >>> from what2.debug import dbg
    >>> @dbg()
    ... def foo(arg: int) -> str:
    ...     return str(arg)
    >>> @dbg(enabled=True)
    ... def bar(arg: int) -> str:
    ...     return str(arg)
    >>> foo_ret = foo(4)
    foo called with args: (4,) and kwargs: {}
    foo, result: 4
    >>> bar_ret = bar(7)
    bar called with args: (7,) and kwargs: {}
    bar, result: 7
    >>> with dbg(enabled=False):
    ...     foo_ret = foo(4)
    ...     bar_ret = bar(7)
    bar called with args: (7,) and kwargs: {}
    bar, result: 7

    Output can be configured within a context:
    >>> from what2.debug import dbg
    >>> a = ["hello", "world"]
    >>> with dbg(with_type=True):
    ...     dbg(5)
    ...     dbg(a)
    5, <class 'int'>: 5
    <BLANKLINE>
    a, <class 'list'>: ['hello', 'world']
    <BLANKLINE>
    >>> with dbg(with_id=True): # doctest: +ELLIPSIS
    ...     dbg(a)
    a, id[...]: ['hello', 'world']
    <BLANKLINE>

    It can be called with a mix of expressions and arguments:
    >>> from what2.debug import dbg
    >>> a = ["hello", "world"]
    >>> dbg(
    ...     a,
    ...     "foo",
    ... )
    a: ['hello', 'world']
    "foo": foo
    <BLANKLINE>

    Doctest Examples
    ----------------
    >>> from what2.debug import dbg
    >>> dbg(3+4)
    3+4: 7
    <BLANKLINE>
    >>> a = ["hello", "world"]
    >>> dbg(a)
    a: ['hello', 'world']
    <BLANKLINE>
    >>> dbg([chunk for chunk in a])
    [chunk for chunk in a]: ['hello', 'world']
    <BLANKLINE>
    >>> @dbg()
    ... def foo(arg: int) -> str:
    ...     return str(arg)
    >>> @dbg(enabled=True)
    ... def bar(arg: int) -> str:
    ...     return str(arg)
    >>> foo_ret = foo(4)
    foo called with args: (4,) and kwargs: {}
    foo, result: 4
    >>> bar_ret = bar(7)
    bar called with args: (7,) and kwargs: {}
    bar, result: 7
    >>> with dbg(enabled=False):
    ...     foo_ret = foo(4)
    ...     bar_ret = bar(7)
    bar called with args: (7,) and kwargs: {}
    bar, result: 7
    >>> with dbg(with_type=True):
    ...     dbg(5)
    ...     dbg(a)
    5, <class 'int'>: 5
    <BLANKLINE>
    a, <class 'list'>: ['hello', 'world']
    <BLANKLINE>
    >>> with dbg(with_id=True): # doctest: +ELLIPSIS
    ...     dbg(a)
    a, id[...]: ['hello', 'world']
    <BLANKLINE>
    >>> dbg(a, "foo")
    a: ['hello', 'world']
    "foo": foo
    <BLANKLINE>
    >>> dbg(
    ...     a,
    ...     "foo",
    ... )
    a: ['hello', 'world']
    "foo": foo
    <BLANKLINE>
    """
    default_dbg = Debug.default()
    match len(args), len(kwargs):
        case 0, 0:
            return DebugProxy(default_dbg, None)
        case 0, _:
            if "store" not in kwargs:
                return DebugProxy(default_dbg, kwargs)
            if "with_type" in kwargs:
                default_dbg.with_type = kwargs["with_type"]
            if "with_id" in kwargs:
                default_dbg.with_id = kwargs["with_id"]
            if "enabled" in kwargs:
                default_dbg.enabled = kwargs["enabled"]
        case _, 0:
            return default_dbg.dbg(*args, frame_depth=2)
        case _, _:
            if "store" in kwargs:
                raise ValueError
            return default_dbg.dbg(*args, frame_depth=2, **kwargs)
