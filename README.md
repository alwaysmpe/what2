# What2

A collection of my random dev tools and scripts.

## PyTest plugin

Adds the following marks:
* `@pytest.mark.nix` - Unix-only tests, equivalent to `@pytest.mark.skipif(condition='sys.platform != "win32"', reason="nix-only test")`
* `@pytest.mark.win` - Windows-only tests, equivalent to `@pytest.mark.skipif(condition='sys.platform == "win32"', reason="win-only test")`
* `@pytest.mark.todo` - skips the test, showing its short status as `t` and long status as `TODO`.
* `@pytest.mark.must_fail(raises=T)` - similar to `@pytest.mark.xfail(strict=True, raises=T)`, however the test is marked as `passed` if it raises the correct exception and `failed` otherwise (for those that don't like the pesky `x` that will never be removed).

## `dbg` function

```python
>>> from what2.debug import dbg
>>> a = ["hello", "world"]
>>> dbg(
...     a,
...     "foo",
... )
a: ['hello', 'world']

"foo": foo

>>> from what2.debug import dbg
>>> dbg(3+4)
3+4: 7

>>> a = ["hello", "world"]
>>> dbg(a)
a: ['hello', 'world']

>>> @dbg()
... def foo(arg: int) -> str:
...     return str(arg)
>>> _ = foo(4)
foo called with args: (4,) and kwargs: {}
foo, result: 4
>>> with dbg(enabled=False):
...     _ = foo(4)
>>> with dbg(with_type=True):
...     dbg(5)
...     dbg(a)
5, <class 'int'>: 5

a, <class 'list'>: ['hello', 'world']

>>> with dbg(with_id=True):
...     dbg(a)
a, id[...]: ['hello', 'world']

>>> dbg(a, "foo")
a: ['hello', 'world']
"foo": foo

>>> dbg(
...     a,
...     "foo",
... )
a: ['hello', 'world']
"foo": foo

```

