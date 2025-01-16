"""
Implementation of `dbg` function.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, field
from functools import cache, wraps
import inspect
from typing import Literal, NotRequired, Self, TypedDict, Unpack, final, overload, override
from unittest.mock import patch
import warnings

import regex

from what2.debug.notebook import is_notebook

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
from types import TracebackType

type DebugImplT = _DebugImpl


@final
@dataclass
class _DebugImpl(AbstractContextManager[DebugImplT]):
    with_type: bool = False
    with_id: bool = False
    enabled: bool = True

    @staticmethod
    @cache
    def argsplit_re() -> regex.Pattern[str]:
        arg_cap = r""" *(\w+) *"""
        qote_cap = r""" *((?P<qseq>(?P<qch>["'])(?:(?P=qch){2})?).*?(?<!\\)(?P=qseq)) *"""
        call_cap = r""" *\w+\((?: *(?&expr)( *,? *(?&expr))*)\) *"""
        num_cap = r""" *(\d*(?:\.\d*)?) *"""
        seq_cap = r""" *(?:(?P<sd>\{)|(?P<lst>\[)|(?P<tp>\()) *(?P<kv>(?&expr) *(?:: *(?&expr))? *(?:, *(?&kv) *)*,? *)(?(lst)\])(?(tp)\))(?(sd)\}) *"""
        fn_break = fr"""^ *\w+\((?:(?P<arg>(?P<expr>{arg_cap}|{qote_cap}|{call_cap}|{num_cap}|{seq_cap}) *(?:[-+*/] *(?&expr))*)(?:, *(?&arg))*) *(?:, *\w* *= *True *)*\) *(?:\#.*)?$"""
        return regex.compile(fn_break)

    @classmethod
    @cache
    def default(cls) -> Self:
        return cls()

    @property
    def installed(self) -> bool:
        return getattr(builtins, "dbg", None) is self

    def install(self) -> None:
        current = getattr(builtins, "dbg", None)

        if current is None:
            return setattr(builtins, "dbg", self)

        if current is not self:
            raise ValueError("different dbg instance already installed.")

    def uninstall(self) -> None:
        current = getattr(builtins, "dbg", None)
        if current is self:
            return delattr(builtins, "dbg")
        if current is not None:
            raise ValueError("different dbg installed but asked to uninstall.")

    def dbg(self, *args: *tuple[object, *tuple[object, ...]], frame_depth: int = 1, **kwargs: Unpack[_DbgKwargs]) -> None:
        """
        Print the expression this function is called with and the value of that expression.

        Inspects the stack to retrieve the expression the function was called with.
        Also tries to format in a notebook environment.

        Note: passing variables that uniquely identify values
        will be faster than passing aliased or literal values
        as getting variable expressions for the latter requires
        parsing the calling code, the former variable names can
        be inferred from callers `local` and `global` variables.

        :param args: The values to be printed.
        :param frame_depth: If calling via proxy, set the stack
            depth to inspect for variable names.
        """
        if not kwargs.get("enabled", self.enabled):
            return None

        current_frame = inspect.currentframe()
        if current_frame is None:
            raise RuntimeError("Unable to inspect current stack frame")

        def print_defs(arg_names: list[tuple[str, object]]) -> None:
            with_id = kwargs.get("with_id", self.with_id)
            with_type = kwargs.get("with_type", self.with_type)

            for raw_arg_name, arg in arg_names:
                arg_name = raw_arg_name.strip(" ,")
                if with_id and with_type:
                    arg_description = f"{arg_name}, {type(arg)} id[{id(arg)}]:"
                elif with_id:
                    arg_description = f"{arg_name}, id[{id(arg)}]:"
                elif with_type:
                    arg_description = f"{arg_name}, {type(arg)}:"
                else:
                    arg_description = f"{arg_name}:"
                if in_notebook and display is not None and Html is not None:
                    display(Html(f"<h5>{arg_description}</h5>"))
                    display(arg)
                else:
                    print(arg_description, arg, sep="\n", end="\n\n")

        parent_frame = inspect.getouterframes(current_frame)[frame_depth]

        arg_names: list[tuple[str, object]] = []
        for arg in args:
            found_count = 0
            for name, var in parent_frame[0].f_locals.items():
                if arg is var:
                    arg_names.append((name, var))
                    found_count += 1
            for name, var in parent_frame[0].f_globals.items():
                if arg is var:
                    arg_names.append((name, var))
                    found_count += 1

            if found_count != 1:
                break
        else:
            return print_defs(arg_names)

        first_line = parent_frame.lineno - 1
        line_offset = parent_frame[0].f_code.co_firstlineno - 1
        current_byte_op = parent_frame[0].f_lasti
        last_line = 0
        for first_byte, _last_bytes, line_no in parent_frame[0].f_code.co_lines():
            if line_no is None:
                continue
            if (first_byte > current_byte_op) and (line_no > first_line):
                last_line = max((last_line, line_no - 1))
                break
            last_line = max((last_line, line_no))
        else:
            last_line = None
        if (last_line is not None) and (first_line > last_line):
            warnings.warn("unable to extract frame info, dbg doesn't work well in optimized modes, windows isn't yet well supported.", stacklevel=frame_depth)
            print(*args)
            return None

        first_line -= line_offset
        if last_line is not None:
            last_line -= line_offset

        call_code = inspect.getsource(parent_frame[0]).splitlines()[first_line:last_line]
        call_code = "".join(call_code)

        split_pat = self.argsplit_re()
        arg_match = split_pat.match(call_code)
        if arg_match is None and ";" in call_code:
            call_code = [
                chunk
                for chunk in call_code.split(";")
                if len(chunk.strip()) > 0
            ]
            call_code = call_code[-1]
            arg_match = split_pat.match(call_code)

        if arg_match is None:
            warnings.warn("unable to extract call arg names. raise an issue and use simpler call syntax.", stacklevel=frame_depth)
            print(*args)
            return None

        cap_names = arg_match.captures("arg")
        cap_names = [cap for cap in cap_names if len(cap) > 0]
        if len(cap_names) != len(args):
            warnings.warn("extracted incorrect number of arg names. raise an issue and use simpler call syntax.", stacklevel=frame_depth)
            print(*args)
            return None
        return print_defs(list(zip(cap_names, args, strict=True)))

    __stack: list[ExitStack] = field(default_factory=list, init=False)

    @override
    def __enter__(self) -> Self:
        state = ExitStack()
        state.enter_context(patch.dict(self.__dict__))
        self.__stack.append(state)
        return self

    @override
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None, /) -> None:
        self.__stack.pop().close()

    def __call__[**P, R](self, fn: Callable[P, R], **call_kwargs: Unpack[_EnableKwarg]) -> Callable[P, R]:
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
class _Debug[CfgT: (_DbgKwargs, _EnableKwarg, None)](AbstractContextManager[None]):
    impl: _DebugImpl
    kwargs: CfgT

    @override
    def __enter__(self: _Debug[_DbgKwargs] | _Debug[_EnableKwarg]) -> None:
        impl = self.impl
        kwargs = self.kwargs
        impl.__enter__()

        if "with_type" in kwargs:
            impl.with_type = kwargs["with_type"]
        if "with_id" in kwargs:
            impl.with_id = kwargs["with_id"]
        if "enabled" in kwargs:
            impl.enabled = kwargs["enabled"]

    def __call__[**P, R](self: _Debug[None] | _Debug[_EnableKwarg], fn: Callable[P, R], /) -> Callable[P, R]:
        if self.kwargs is None:
            return self.impl(fn)
        return self.impl(fn, **self.kwargs)

    @override
    def __exit__(self: _Debug[_DbgKwargs], exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None, /) -> None:
        return self.impl.__exit__(exc_type, exc_value, traceback)


@overload
def dbg() -> _Debug[None]:
    ...


@overload
def dbg(
    *,
    enabled: bool,
) -> _Debug[_EnableKwarg]:
    ...


@overload
def dbg(
    *,
    with_type: bool,
    with_id: bool = ...,
    enabled: bool = ...,
) -> _Debug[_DbgKwargs]:
    ...


@overload
def dbg(
    *,
    with_type: bool = ...,
    with_id: bool,
    enabled: bool = ...,
) -> _Debug[_DbgKwargs]:
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


def dbg[**P, R](*args: *tuple[object, ...], **kwargs: Unpack[_CfgKwargs]) -> _Debug[_EnableKwarg] | _Debug[_DbgKwargs] | _Debug[None] | None:
    """
    Single function to configurably render arbitrary variable names and values.

    This function has several modes of use:

    * Call without arguments to use as a function decorator, or with `enabled` to explicitly enable/disable the decorator.
    * Call with option keywords and `store=True` to configure how a value is rendered.
    * Call with option keywords without `store` to temoprarily configure within a context.
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
    a:
    ['hello', 'world']
    <BLANKLINE>
    "foo":
    foo
    <BLANKLINE>

    This includes expressions:
    >>> from what2.debug import dbg
    >>> dbg(3+4)
    3+4:
    7
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
    5, <class 'int'>:
    5
    <BLANKLINE>
    a, <class 'list'>:
    ['hello', 'world']
    <BLANKLINE>
    >>> with dbg(with_id=True): # doctest: +ELLIPSIS
    ...     dbg(a)
    a, id[...]:
    ['hello', 'world']
    <BLANKLINE>

    It can be called with a mix of expressions and arguments:
    >>> from what2.debug import dbg
    >>> a = ["hello", "world"]
    >>> dbg(
    ...     a,
    ...     "foo",
    ... )
    a:
    ['hello', 'world']
    <BLANKLINE>
    "foo":
    foo
    <BLANKLINE>

    Doctest Examples
    ----------------
    >>> from what2.debug import dbg
    >>> dbg(3+4)
    3+4:
    7
    <BLANKLINE>
    >>> a = ["hello", "world"]
    >>> dbg(a)
    a:
    ['hello', 'world']
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
    5, <class 'int'>:
    5
    <BLANKLINE>
    a, <class 'list'>:
    ['hello', 'world']
    <BLANKLINE>
    >>> with dbg(with_id=True): # doctest: +ELLIPSIS
    ...     dbg(a)
    a, id[...]:
    ['hello', 'world']
    <BLANKLINE>
    >>> dbg(a, "foo")
    a:
    ['hello', 'world']
    <BLANKLINE>
    "foo":
    foo
    <BLANKLINE>
    >>> dbg(
    ...     a,
    ...     "foo",
    ... )
    a:
    ['hello', 'world']
    <BLANKLINE>
    "foo":
    foo
    <BLANKLINE>
    """
    default_dbg = _DebugImpl.default()
    match len(args), len(kwargs):
        case 0, 0:
            return _Debug(default_dbg, None)
        case 0, _:
            if "store" not in kwargs:
                return _Debug(default_dbg, kwargs)
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
