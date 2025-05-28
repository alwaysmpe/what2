# What2

A collection of my random dev tools and scripts.

## `dbg` function

```python
>>> from what2.debug import dbg
>>> a = ["hello", "world"]
>>> dbg(
...     a,
...     "foo",
... )
a:
['hello', 'world']

"foo":
foo

>>> from what2.debug import dbg
>>> dbg(3+4)
3+4:
7

>>> a = ["hello", "world"]
>>> dbg(a)
a:
['hello', 'world']

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
5, <class 'int'>:
5

a, <class 'list'>:
['hello', 'world']

>>> with dbg(with_id=True): # doctest: +ELLIPSIS
...     dbg(a)
a, id[...]:
['hello', 'world']

>>> dbg(a, "foo")
a:
['hello', 'world']

"foo":
foo

>>> dbg(
...     a,
...     "foo",
... )
a:
['hello', 'world']

"foo":
foo

```
