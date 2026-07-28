from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NodeResources:
    cpu_m: int
    mem_mib: int

@dataclass
class DeploymentResources:
    cpu_m: int
    mem_mib: int
    running_pods: int


@dataclass
class PodResources:
    cpu_m: int
    mem_mib: int


@dataclass
class NodeUtilisation:
    cpu_pct: float
    mem_pct: float

@dataclass
class DeploymentUtilisation:
    cpu_pct: float
    mem_pct: float

@dataclass
class PodUtilisation:
    cpu_pct: float
    mem_pct: float