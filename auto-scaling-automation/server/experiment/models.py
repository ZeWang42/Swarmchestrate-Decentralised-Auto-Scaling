from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

from config import DEFAULT_NAMESPACE, PROM_URL


class DeployAppRequest(BaseModel):
    namespace: str = Field(default=DEFAULT_NAMESPACE, description="Target namespace")
    manifest_path: str = Field(description="Path to application manifest")
    gateway_manifest_path: str | None = Field(default=None, description="Optional path to gateway/virtual service manifest")
    create_namespace: bool = Field(default=False, description="Create namespace if it does not exist")


class DeployAppResponse(BaseModel):
    ok: bool
    message: str
    app: str
    namespace: str
    applied_files: list[str]
    gateway_url_hint: str | None = None


class DeployAutoscalerRequest(BaseModel):
    namespace: str = Field(default=DEFAULT_NAMESPACE, description="Target namespace")
    deployment_names: list[str] | None = Field(default=None, description="Optional target deployments; defaults to all known deployments present for the app")
    autoscaler_name: str = Field(description="Autoscaler folder name, e.g. default_cpu, das, customdas, dadqn, pbscaler, or none")
    config: dict[str, Any] = Field(default_factory=dict, description="Autoscaler-specific parameters")


class DeployAutoscalerResponse(BaseModel):
    ok: bool
    app: str
    namespace: str
    autoscaler_name: str
    results: list[dict[str, Any]]


class DeleteAutoscalerResponse(BaseModel):
    ok: bool
    app: str
    namespace: str
    autoscaler_name: str
    deleted_resources: list[str]
    missing_resources: list[str]
    errors: list[str]


class StartMonitorRequest(BaseModel):
    namespace: str = Field(default=DEFAULT_NAMESPACE, description="Target namespace")
    interval: int = Field(default=5, ge=1, description="Sampling interval in seconds")
    prom_url: str = Field(default=PROM_URL, description="Prometheus instant query API URL")
    file_prefix: str = Field(default="mesh_metrics", description="Prefix for output CSV file name")
    autoscaler_name: str | None = Field(
        default=None,
        description="Optional deployed autoscaler name whose controller pods should also be monitored",
    )
    latency_percentile: Literal["p90", "p95"] = Field(
        default="p95",
        description="Application latency percentile collected by the monitor",
    )


class MonitorStatusResponse(BaseModel):
    ok: bool
    running: bool
    namespace: str | None = None
    interval: int | None = None
    prom_url: str | None = None
    autoscaler_name: str | None = None
    latency_percentile: str | None = None
    log_file: str | None = None
    started_at: str | None = None


class AutoscalerExperimentConfig(BaseModel):
    autoscaler_name: str = Field(description="default_cpu, das, customdas, dadqn, pbscaler, or none")
    deployment_names: list[str] | None = Field(default=None, description="Optional deployments that should receive the autoscaler")
    config: dict[str, Any] = Field(default_factory=dict)


class LegacyHPAExperimentConfig(BaseModel):
    mode: str = Field(description="cpu or none")
    target_cpu_utilization: int | None = Field(default=None)
    min_replicas: int = Field(default=1, ge=1)
    max_replicas: int = Field(default=10, ge=1)
    deployment_names: list[str] | None = Field(default=None, description="Optional deployments to attach the HPA to")


class MonitorExperimentConfig(BaseModel):
    interval: int = Field(default=5, ge=1)
    prom_url: str = Field(default=PROM_URL)
    file_prefix: str = Field(default="mesh_metrics")
    latency_percentile: Literal["p90", "p95"] = Field(
        default="p95",
        description="Application latency percentile collected by the monitor",
    )


class ExperimentSetupRequest(BaseModel):
    app: str = Field(default="bookinfo")
    namespace: str = Field(default=DEFAULT_NAMESPACE)
    workload_name: str | None = Field(default=None, description="Workload profile name, e.g. constant-100 or wiki_load")
    duration_seconds: int = Field(default=120, ge=1)
    autoscaler: AutoscalerExperimentConfig | None = Field(default=None)
    hpa: LegacyHPAExperimentConfig | None = Field(default=None, description="Backward-compatible client payload")
    monitor: MonitorExperimentConfig = Field(default_factory=MonitorExperimentConfig)

    @model_validator(mode="after")
    def normalize_autoscaler(self) -> "ExperimentSetupRequest":
        if self.autoscaler is not None:
            return self

        if self.hpa is None:
            raise ValueError("Either autoscaler or hpa must be provided")

        mode = self.hpa.mode.strip().lower()
        deployment_names = self.hpa.deployment_names

        if mode == "none":
            self.autoscaler = AutoscalerExperimentConfig(
                autoscaler_name="none",
                deployment_names=deployment_names,
                config={},
            )
            return self

        if mode == "cpu":
            if self.hpa.target_cpu_utilization is None:
                raise ValueError("hpa.target_cpu_utilization is required when hpa.mode='cpu'")
            self.autoscaler = AutoscalerExperimentConfig(
                autoscaler_name="default_cpu",
                deployment_names=deployment_names,
                config={
                    "min_replicas": self.hpa.min_replicas,
                    "max_replicas": self.hpa.max_replicas,
                    "average_cpu_utilization": self.hpa.target_cpu_utilization,
                },
            )
            return self

        raise ValueError(f"Unsupported hpa.mode: {self.hpa.mode}")


class ExperimentSetupResponse(BaseModel):
    ok: bool
    app: str
    namespace: str
    workload_name: str | None
    duration_seconds: int
    autoscaler_name: str
    autoscaler_result: dict[str, Any] | None = None
    monitor_result: dict[str, Any] | None = None
    ready_for_load: bool


class ExperimentCleanupRequest(BaseModel):
    app: str = Field(default="bookinfo")
    namespace: str = Field(default=DEFAULT_NAMESPACE)
    autoscaler_name: str = Field(default="none")
    deployment_names: list[str] | None = Field(default=None, description="Optional autoscaler target deployments to remove")
    delete_autoscaler: bool = Field(default=True)
    delete_hpa: bool | None = Field(default=None, description="Backward-compatible alias for delete_autoscaler when using the legacy client")
    stop_monitoring: bool = Field(default=True)

    @model_validator(mode="after")
    def normalize_cleanup_flags(self) -> "ExperimentCleanupRequest":
        if self.delete_hpa is not None:
            self.delete_autoscaler = self.delete_hpa
            if self.delete_hpa:
                self.autoscaler_name = "default_cpu"
        return self
