from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScaleResult:
    deployment_name: str
    previous_replicas: int
    desired_replicas: int
    applied: bool
