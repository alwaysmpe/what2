import os
from pathlib import Path
import shlex
import subprocess

import pytest

base_dir = Path(__file__).absolute().parent.parent


def is_linux() -> bool:
    return os.name == "posix"


def call(cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=base_dir, check=False)
    if is_linux():
        redirect = " 2>&1 | head -n 30"
        cmd = ["unbuffer", *cmd]
    else:
        redirect = ""

    expanded_command = shlex.join(cmd) + redirect
    print("command run:", expanded_command)
    if result.returncode == 0:
        return

    raise Exception("Command returned error: " + expanded_command)


def pyright(path: Path):
    call(["basedpyright", str(path), "-p", str(path)])


def ruff(path: Path):
    call(["ruff", "check", str(path), "--preview"])


def darglint(path: Path):
    call([
        "darglint2",
        str(path / "src"),
        str(path / "tests"),
    ])


def deptry_src(path: Path):
    call([
        "deptry",
        "-kf", "what2",
        str(path / "src"),
    ])


def deptry_test(path: Path):
    call([
        "deptry",
        "--ignore",
        "DEP004,DEP002",
        "-kf", "what2",
        "-kf", "tests",
        str(path / "tests"),
    ])


def pylama(path: Path):
    call([
        "pylama",
        str(path / "src"),
        str(path / "tests"),
    ])


@pytest.mark.order(-4)
def test_static_type_analysis():
    pyright(base_dir)


@pytest.mark.order(-3)
def test_linter():
    ruff(base_dir)


@pytest.mark.order(-2)
def test_code_audit():
    pylama(base_dir)


@pytest.mark.order(-2)
def test_dependencies():
    deptry_src(base_dir)
    deptry_test(base_dir)


@pytest.mark.xfail(reason="darglint doesn't handle typed dict kwargs...")
@pytest.mark.order(-1)
def test_doc_linter():
    return darglint(base_dir)
