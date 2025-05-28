from functools import partial
import sys

from what2_time import Timer

from what2.debug import dbg

import pytest


def test_ctx(capsys: pytest.CaptureFixture[str]):

    a = ["hello", "world"]

    def get_stdout() -> str:
        out_err = capsys.readouterr()
        print(out_err.err, file=sys.stderr, end="")
        print(out_err.out, file=sys.stderr, end="")
        return out_err.out

    def name_in_out(name: str, val: object, stdout: str) -> bool:
        return f"{name}: {val}" in stdout

    has_a = partial(name_in_out, "a", a)
    dbg(a)

    assert has_a(get_stdout())
    b = 3
    has_b = partial(name_in_out, "b", b)

    dbg(a, b)
    stdout = get_stdout()
    assert has_a(stdout)
    assert has_b(stdout)
    with Timer():
        dbg(b, a)
    stdout = get_stdout()
    assert has_a(stdout)
    assert has_b(stdout)
    with Timer():
        dbg(
            a,
            "foo",
        ) # trailing comments no prob
    # assert 0
    stdout = get_stdout()
    print(stdout)
    assert has_a(stdout)
    assert '"foo": foo' in stdout
    dbg(a,
        "bar")
    stdout = get_stdout()
    assert has_a(stdout)
    assert '"bar": bar' in stdout


def test_slice(capsys: pytest.CaptureFixture[str]):
    vals = ["abc", "def"]
    dbg(vals[0])
    output = capsys.readouterr().out
    print(output)
    assert "vals[0]: abc" in output
