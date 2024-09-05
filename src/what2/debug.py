"""
Code useful for debugging.
"""
import inspect
from typing import Any

from what2.inspect import is_notebook

try:
    from IPython.display import HTML, display
    in_notebook = is_notebook()
except ImportError:
    if is_notebook():
        raise
    in_notebook = False


def dbg(arg: Any) -> None:
    """
    Print the expression dbg is called with and the value of that expression.

    Inspects the stack to retrieve the expression the function was called with.
    Also tries to format in a notebook environment.

    :param arg: The value to be printed.

    Examples
    --------
    >>> dbg(3+4)
    3+4: 7
    >>> a = ["hello", "world"]
    >>> dbg(a)
    a: ['hello', 'world']
    """
    current_frame = inspect.currentframe()
    if current_frame is None:
        raise RuntimeError("Unable to inspect current stack frame")

    parent_frame = inspect.getouterframes(current_frame)[1]
    call_context = inspect.getframeinfo(parent_frame[0]).code_context
    if call_context is None:
        raise RuntimeError("Unable to inspect calling code")

    string = call_context[0].strip()
    arg_name = string[string.find("(") + 1:-1]
    if in_notebook:
        display(HTML(f"<h5>{arg_name}</h5>"))
        display(arg)
    else:
        print(f"{arg_name}:", arg, sep='\n', end='\n\n') # noqa: T201
