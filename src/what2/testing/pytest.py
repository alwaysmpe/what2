from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, is_dataclass
from inspect import getmodule
from pathlib import Path
import string
import sys
from types import FunctionType, MethodType
from typing import Any, TypeGuard, override

import pytest

from _pytest.python import pytest_pycollect_makeitem as _make_item
from _pytest.runner import pytest_runtest_makereport as _make_report


def is_win() -> bool:
    return sys.platform == "win32"


def pytest_configure(config: pytest.Config):
    config.addinivalue_line("markers", "win: windows only tests")
    config.addinivalue_line("markers", "nix: unix only tests")
    config.addinivalue_line("markers", "must_fail: tests where failure is successs and vice versa")
    config.addinivalue_line("markers", "todo: incomplete tests")


def pytest_addoption(parser: pytest.Parser) -> None:
    return
    # parser.addini(
    #     name=
    # )


def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> pytest.TestReport | None:
    markers = {
        mark.name: mark
        for mark in item.iter_markers()
    }

    if (
        "must_fail" in markers
        and (kls := markers["must_fail"].kwargs.get("raises")) is not None
        and call.excinfo is not None
        and call.excinfo.type is kls
    ):
        report = _make_report(item, call)
        report.outcome = "passed"
        return report


def pytest_report_teststatus(report: pytest.CollectReport | pytest.TestReport) -> None | tuple[str, str, str | Mapping[str, bool]]:
    if isinstance(report, pytest.CollectReport):
        return None

    if "todo" in report.keywords and report.when == "setup":
        return "TODO", "t", "to-do"


def pytest_itemcollected(item: pytest.Function):
    markers = {
        mark.name: mark
        for mark in item.iter_markers()
    }

    if "todo" in markers:
        item.add_marker(pytest.mark.skip(reason="to do"))

    nix = markers.get("nix")
    win = markers.get("win")
    os_marker = nix if is_win() else win

    if win and nix:
        item.warn(UserWarning("nix and win markers used together."))
    elif os_marker is not None:
        item.add_marker(pytest.mark.skip(f"{os_marker.name}-only test"))


def is_type[T](obj: T | type[T]) -> TypeGuard[type[T]]:
    return isinstance(obj, type)


def pytest_pycollect_makeitem[T](
    collector: pytest.Module | pytest.Class, name: str, obj: T | type[T],
) -> None | pytest.Item | pytest.Collector | list[pytest.Item | pytest.Collector]:
    return None
    item = _make_item(collector, name, obj)

    if isinstance(item, pytest.Class) and is_type(obj):
        if not is_dataclass(obj):
            obj = dataclass(frozen=True, init=False)(obj)
        return FilterClass.from_parent(collector, name=name, obj=obj) # type: ignore[reportUnknownMemberType]
    return item


def pytest_pycollect_makemodule(
    module_path: Path, parent: Any,
) -> pytest.Module | None:
    return None
    return FilterModule.from_parent(parent, path=module_path) # type: ignore[reportUnknownArgumentType]


class FilterModule(pytest.Module):
    @override
    def istestclass(self, obj: object, name: str) -> bool:
        return super().istestclass(obj, name) and (getmodule(obj) is self.obj)

    @override
    def istestfunction(self, obj: object, name: str) -> bool:
        if not super().istestfunction(obj, name):
            return False
        if getmodule(obj) is not self.obj:
            return False
        if not isinstance(obj, FunctionType | MethodType):
            return False
        name = obj.__name__
        return name.startswith("test_")


class FilterClass(pytest.Class):
    @override
    def istestfunction(self, obj: object, name: str) -> bool:
        cls: type[Any] = self.obj
        if name in {
            "setup",
            "setup_method",
            "teardown",
            "teardown_method",
        }:
            self.warn(pytest.PytestWarning(f"Setup method in class {cls.__qualname__}"))
            return False
        if name[0] in string.ascii_uppercase:
            self.warn(pytest.PytestWarning(f"Upper case test function name in class {cls.__qualname__}, fn: {name}"))
            return True

        return super().istestfunction(obj, name) and isinstance(obj, FunctionType)

    @override
    def istestclass(self, obj: object, name: str) -> bool:
        cls: type[Any] = self.obj
        if name.lower() != name:
            self.warn(pytest.PytestWarning(f"Upper case nested test class {cls.__qualname__}"))

        return super().istestclass(obj, name)
