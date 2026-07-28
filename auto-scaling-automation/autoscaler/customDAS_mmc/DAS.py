from __future__ import annotations

import logging
import math
import os
import statistics
import time
from collections import deque
from typing import Any

from kubernetes import config

from monitoring import Monitor


LOG_FILE = os.getenv("LOG_FILE", "/tmp/cpu_process_time.log")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE),
        ],
        force=True,
    )


def valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) >= 0.0


def median_or_nan(values: list[float]) -> float:
    clean = [float(v) for v in values if valid_number(v) and v > 0.0]
    if not clean:
        return float("nan")
    return float(statistics.median(clean))


def get_cpu_capacity_mcores(deployment: str, pods_count: int) -> float | None:
    """Optional CPU-capacity denominator for effective service time.

    Set either:
      CPU_CAPACITY_MCORES=<per-pod mCPU capacity>
      CPU_REQUEST_MCORES=<per-pod request mCPU>
      CPU_LIMIT_MCORES=<per-pod limit mCPU>

    If none is set, the script still reports raw CPU demand only:
      cpu_demand_ms = cpu_used_cores / lambda_rps * 1000
    """
    for env_name in (
        f"CPU_CAPACITY_MCORES_{deployment.upper().replace('-', '_')}",
        "CPU_CAPACITY_MCORES",
        f"CPU_LIMIT_MCORES_{deployment.upper().replace('-', '_')}",
        "CPU_LIMIT_MCORES",
        f"CPU_REQUEST_MCORES_{deployment.upper().replace('-', '_')}",
        "CPU_REQUEST_MCORES",
    ):
        raw = os.getenv(env_name)
        if raw not in (None, ""):
            per_pod = float(raw)
            return per_pod * max(1, pods_count)
    return None


def cpu_process_time_loop(monitor: Monitor, deployment: str, interval: float) -> None:
    max_samples = int(os.getenv("CPU_PROCESS_TIME_MAX_SAMPLES", "200"))
    warmup_samples = int(os.getenv("CPU_PROCESS_TIME_WARMUP_SAMPLES", "1"))
    min_lambda_rps = float(os.getenv("MIN_LAMBDA_RPS", "0.001"))

    samples_cpu_demand_ms: deque[float] = deque(maxlen=max_samples)
    samples_effective_ms: deque[float] = deque(maxlen=max_samples)

    logging.info(
        "[CPU PROCESS TIME MONITOR START] deployment=%s interval=%.1fs max_samples=%d warmup_samples=%d",
        deployment,
        interval,
        max_samples,
        warmup_samples,
    )

    while True:
        try:
            resources = monitor.get_deployment_resources(deployment)
            cpu_m = float(resources.cpu_m or 0.0)
            pods_count = int(resources.running_pods or 0)

            http_rpm = float(monitor.get_http_rpm_as_dst(deployment) or 0.0)
            grpc_rpm = float(monitor.get_grpc_rpm_as_dst(deployment) or 0.0)
            lambda_rps = (http_rpm + grpc_rpm) / 60.0

            # Destination-side transit latency for the same deployment.
            # HTTP and gRPC metrics are added, following the original DAS logging convention.
            http_p10_ms = float(monitor.get_http_latency_p10_as_dst(deployment) or 0.0)
            grpc_p10_ms = float(monitor.get_grpc_latency_p10_as_dst(deployment) or 0.0)
            http_p25_ms = float(monitor.get_http_latency_p25_as_dst(deployment) or 0.0)
            grpc_p25_ms = float(monitor.get_grpc_latency_p25_as_dst(deployment) or 0.0)
            http_p50_ms = float(monitor.get_http_latency_p50_as_dst(deployment) or 0.0)
            grpc_p50_ms = float(monitor.get_grpc_latency_p50_as_dst(deployment) or 0.0)
            http_p90_ms = float(monitor.get_http_latency_p90_as_dst(deployment) or 0.0)
            grpc_p90_ms = float(monitor.get_grpc_latency_p90_as_dst(deployment) or 0.0)
            http_p95_ms = float(monitor.get_http_latency_p95_as_dst(deployment) or 0.0)
            grpc_p95_ms = float(monitor.get_grpc_latency_p95_as_dst(deployment) or 0.0)

            latency_p10_ms = http_p10_ms + grpc_p10_ms
            latency_p25_ms = http_p25_ms + grpc_p25_ms
            latency_p50_ms = http_p50_ms + grpc_p50_ms
            latency_p90_ms = http_p90_ms + grpc_p90_ms
            latency_p95_ms = http_p95_ms + grpc_p95_ms

            if pods_count <= 0:
                logging.warning("[SKIP] deployment=%s has no running pods", deployment)
                time.sleep(interval)
                continue

            if not valid_number(lambda_rps) or lambda_rps < min_lambda_rps:
                logging.info(
                    "[SKIP] deployment=%s lambda=%.4f req/s below MIN_LAMBDA_RPS=%.4f",
                    deployment,
                    lambda_rps,
                    min_lambda_rps,
                )
                time.sleep(interval)
                continue

            # CPU demand per request. Numerically, cpu_m / lambda_rps gives
            # core-ms/request because: (mCPU / req/s) == (core-ms/request).
            cpu_demand_ms = cpu_m / lambda_rps
            samples_cpu_demand_ms.append(cpu_demand_ms)

            median_cpu_demand_ms = median_or_nan(list(samples_cpu_demand_ms))

            total_capacity_mcores = get_cpu_capacity_mcores(deployment, pods_count)
            effective_service_time_ms = None
            median_effective_ms = None
            if total_capacity_mcores is not None and total_capacity_mcores > 0:
                # Effective wall-clock service time under the configured CPU capacity.
                # D_cpu / C, where D_cpu is core-ms/request and C is cores.
                effective_service_time_ms = cpu_demand_ms / (total_capacity_mcores / 1000.0)
                samples_effective_ms.append(effective_service_time_ms)
                median_effective_ms = median_or_nan(list(samples_effective_ms))

            ready = len(samples_cpu_demand_ms) >= warmup_samples

            logging.info(
                "[CPU PROCESS TIME] service=%s lambda=%.2f req/s cpu=%dm pods=%d "
                "sample_cpu_demand=%.4fms_cpu_per_req median_cpu_demand=%.4fms_cpu_per_req "
                "samples=%d ready=%s",
                deployment,
                lambda_rps,
                int(round(cpu_m)),
                pods_count,
                cpu_demand_ms,
                median_cpu_demand_ms,
                len(samples_cpu_demand_ms),
                ready,
            )

            logging.info(
                "[LATENCY AS DST] service=%s p10=%.2fms p25=%.2fms p50=%.2fms p90=%.2fms p95=%.2fms",
                deployment,
                latency_p10_ms,
                latency_p25_ms,
                latency_p50_ms,
                latency_p90_ms,
                latency_p95_ms,
            )

            if effective_service_time_ms is not None and median_effective_ms is not None:
                logging.info(
                    "[CPU EFFECTIVE SERVICE TIME] service=%s total_cpu_capacity=%dm "
                    "sample_effective_S=%.4fms median_effective_S=%.4fms samples=%d ready=%s",
                    deployment,
                    int(round(total_capacity_mcores)),
                    effective_service_time_ms,
                    median_effective_ms,
                    len(samples_effective_ms),
                    ready,
                )

        except Exception as exc:
            logging.exception("[ERROR] %s", exc)

        time.sleep(interval)


def main() -> None:
    configure_logging()

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    namespace = os.getenv("NAMESPACE", "default")
    deployment = os.getenv("TARGET_DEPLOYMENT", "frontend")
    interval = float(os.getenv("INTERVAL", os.getenv("NORMAL_DETECTION_INTERVAL_SECONDS", "15")))
    prom_url = os.getenv(
        "PROM_URL",
        "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    )

    monitor = Monitor(namespace=namespace, prom_url=prom_url)
    cpu_process_time_loop(monitor, deployment, interval)


if __name__ == "__main__":
    main()
