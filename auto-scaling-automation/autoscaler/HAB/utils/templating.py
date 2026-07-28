
from __future__ import annotations
from pathlib import Path
import yaml

def render_template(path: str, variables: dict) -> list[dict]:
    content = Path(path).read_text(encoding="utf-8")
    for key, value in variables.items():
        content = content.replace(f"{{{{ {key} }}}}", str(value))
    return [doc for doc in yaml.safe_load_all(content) if doc]
