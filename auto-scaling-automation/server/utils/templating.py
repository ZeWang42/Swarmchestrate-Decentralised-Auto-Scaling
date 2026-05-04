from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def render_string_template(content: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise KeyError(f"Missing template variable: {key}")
        value = variables[key]
        return "" if value is None else str(value)

    return _PLACEHOLDER_PATTERN.sub(replace, content)


def render_template(path: str | Path, variables: dict[str, Any]) -> list[dict]:
    raw = Path(path).read_text(encoding="utf-8")
    rendered = render_string_template(raw, variables)
    return [doc for doc in yaml.safe_load_all(rendered) if doc]
