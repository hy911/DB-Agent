"""Pure types for the vetted statistical-test registry. No library imports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ParamSpec:
    role: str  # "column" | "columns" | "scalar"
    required: bool = True
    py_type: type | None = None  # scalar only: int | float | bool
    bounds: tuple[float, float] | None = None  # scalar numeric: exclusive (lo, hi)
    choices: tuple[object, ...] | None = None  # scalar enum


@dataclass(frozen=True)
class StatResult:
    test: str
    stats: dict[str, float]
    groups: list[dict[str, object]]
    caveats: list[str]


@dataclass(frozen=True)
class StatTest:
    name: str
    description: str
    params: dict[str, ParamSpec]
    run: Callable[[list[dict[str, object]], dict[str, object]], StatResult]


@dataclass(frozen=True)
class ValidatedStatRequest:
    test: StatTest
    params: dict[str, object]
