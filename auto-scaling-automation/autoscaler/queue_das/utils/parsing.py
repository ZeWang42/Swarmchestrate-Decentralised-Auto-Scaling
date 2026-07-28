
from __future__ import annotations
import math

def parse_cpu_to_millicores(value: str) -> int:
    if not value:
        return 0
    try:
        if value.endswith("n"):
            return int(float(value[:-1]) / 1_000_000)
        if value.endswith("u"):
            return int(float(value[:-1]) / 1_000)
        if value.endswith("m"):
            return int(float(value[:-1]))
        return int(float(value) * 1000)
    except ValueError:
        return 0


def parse_memory_to_mib(value: str) -> int:
    if not value:
        return 0

    binary_units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "Pi": 1024 * 1024 * 1024,
        "Ei": 1024 * 1024 * 1024 * 1024,
    }
    decimal_units = {
        "K": 1000 / (1024 * 1024),
        "M": 1000 * 1000 / (1024 * 1024),
        "G": 1000 * 1000 * 1000 / (1024 * 1024),
        "T": 1000 * 1000 * 1000 * 1000 / (1024 * 1024),
    }

    try:
        for unit, factor in binary_units.items():
            if value.endswith(unit):
                return int(float(value[:-len(unit)]) * factor)
        for unit, factor in decimal_units.items():
            if value.endswith(unit):
                return int(float(value[:-len(unit)]) * factor)
        return int(float(value) / (1024 * 1024))
    except ValueError:
        return 0


def round1(value: float | int | None) -> str:
    if value in (None, 0, 0.0):
        return "0.0"
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return "0.0"
        return f"{v:.1f}"
    except (TypeError, ValueError):
        return "0.0"
