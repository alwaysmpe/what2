"""
Code to inspect the environment.
"""
from __future__ import annotations


def is_notebook() -> bool: # numpydoc ignore=ES01,EX01
    """
    Try to determine if we're running in a notebook-like environment (jupyter/ipynotebook/etc).

    :returns: Whether it looks like we're in a supported notebook environment.
    """
    try:
        shell: str = str(get_ipython().__class__.__name__) # type: ignore # noqa: PGH003
        match shell:
            case "ZMQInteractiveShell":
                return True   # Jupyter notebook or qtconsole
            case "TerminalInteractiveShell":
                return False  # Terminal running IPython
            case _:
                return False  # Other type (?)
    except NameError:
        return False          # Probably standard Python interpreter
