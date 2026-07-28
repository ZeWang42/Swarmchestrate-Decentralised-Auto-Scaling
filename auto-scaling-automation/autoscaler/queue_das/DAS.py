from __future__ import annotations

import logging
import os
import time
import math

from kubernetes import config

from monitoring import Monitor
from execution import Executor
from queue_das_logging import build_deployment_monitoring_log

APP_NAME = os.getenv("APP_NAME", "onlineboutique").strip().lower()
ROOT_SERVICE = os.getenv(
    "ROOT_SERVICE",
    "productpage-v1" if APP_NAME == "bookinfo" else "frontend",
).strip()
ROOT_SERVICES = {ROOT_SERVICE} if ROOT_SERVICE else {"frontend"}

P25_FROM_P50_FACTOR = 2.0 / 3.0

BASELINE_PROCESSING_TIME_MS_BY_APP: dict[str, dict[str, float | None]] = {
    "onlineboutique": {
        "frontend": 41.88,
        "cartservice": 4.32,
        "checkoutservice": 38.46,
        "productcatalogservice": 3,
        "recommendationservice": 7.8,
        "currencyservice": 3.06,
        "adservice": 3.05,
        "emailservice": 3.50,
        "paymentservice": 3.12,
        "shippingservice": 3.16,
        "redis-cart": 1.00,
    },
    "bookinfo": {
        "productpage-v1": 17.11,
        "details-v1": 4.02,
        "ratings-v1": 2.94,
        "reviews-v1": 3.30,
        "reviews-v2": 9.06,
        "reviews-v3": 8.68,
    },
}

BASELINE_PROCESSING_TIME_MS: dict[str, float | None] = {
    service: value
    for app_table in BASELINE_PROCESSING_TIME_MS_BY_APP.values()
    for service, value in app_table.items()
}

SELECTED_APP_BASELINE_PROCESSING_TIME_MS: dict[str, float | None] = (
    BASELINE_PROCESSING_TIME_MS_BY_APP.get(APP_NAME, {})
)

LOG_FILE = os.getenv("LOG_FILE", "/tmp/customdas.log")
ENABLE_COLOURED_LOGS = os.getenv("ENABLE_COLOURED_LOGS", "1").strip().lower() not in {"0", "false", "no", "off"}

ANSI_RESET = "\033[0m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"
ANSI_GREEN = "\033[32m"
ANSI_CYAN = "\033[36m"


def colour_text(text: str, colour: str) -> str:
    if not ENABLE_COLOURED_LOGS:
        return text
    return f"{colour}{text}{ANSI_RESET}"


class ConsoleColourFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not ENABLE_COLOURED_LOGS:
            return message
        raw_message = record.getMessage()
        if record.levelno >= logging.ERROR or "[ERROR]" in raw_message:
            return f"{ANSI_RED}{message}{ANSI_RESET}"
        if record.levelno == logging.WARNING:
            return f"{ANSI_YELLOW}{message}{ANSI_RESET}"
        return message


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import re
        message = super().format(record)
        return re.sub(r"\x1b\[[0-9;]*m", "", message)


def configure_logging() -> None:
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleColourFormatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(PlainFormatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


configure_logging()


def valid_number(x: float) -> bool:
    return x is not None and math.isfinite(x) and x >= 0


def median(values: list[float]) -> float | None:
    clean = sorted(float(v) for v in values if valid_number(v) and v > 0)
    if not clean:
        return None
    n = len(clean)
    mid = n // 2
    if n % 2 == 1:
        return clean[mid]
    return 0.5 * (clean[mid - 1] + clean[mid])


def mean(values: list[float]) -> float | None:
    clean = [float(v) for v in values if valid_number(v) and v > 0]
    if not clean:
        return None
    return sum(clean) / len(clean)


def percentile(values: list[float], q: float) -> float | None:
    clean = sorted(float(v) for v in values if valid_number(v) and v > 0)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    q = max(0.0, min(1.0, q))
    pos = (len(clean) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return clean[lo]
    return clean[lo] * (hi - pos) + clean[hi] * (pos - lo)


def get_baseline_processing_time_s(deployment: str) -> tuple[float | None, str]:
    baseline_ms = SELECTED_APP_BASELINE_PROCESSING_TIME_MS.get(deployment)
    if baseline_ms is None:
        baseline_ms = BASELINE_PROCESSING_TIME_MS.get(deployment)
    if baseline_ms is not None:
        processing_ms = float(baseline_ms) * P25_FROM_P50_FACTOR
        return processing_ms / 1000.0, f"calibrated_p25_from_p50_table_{APP_NAME}"
    return None, "runtime_fallback_p25"


def normalize_latency_percentile(raw: str | None, default: str = "p95") -> tuple[str, float]:
    value = (raw or default).strip().lower().replace(" ", "")
    aliases = {
        "p90": ("P90", 0.90),
        "90": ("P90", 0.90),
        "0.90": ("P90", 0.90),
        "0.9": ("P90", 0.90),
        "p95": ("P95", 0.95),
        "95": ("P95", 0.95),
        "0.95": ("P95", 0.95),
    }
    if value not in aliases:
        logging.warning(
            "Unsupported SLO_LATENCY_PERCENTILE=%r; falling back to %s",
            raw,
            default,
        )
        return aliases[default]
    return aliases[value]


def get_configured_latency_slo_ms() -> float:
    default_slo = os.getenv("SLO_MS", os.getenv("SLO_LATENCY_MS", "500"))
    return float(os.getenv("LATENCY_SLO_MS", default_slo))


def erlang_c(lambda_rps: float, mu: float, c: int) -> float:
    if not valid_number(lambda_rps) or not valid_number(mu):
        return float("nan")
    if c <= 0 or mu <= 0:
        return float("nan")
    rho = lambda_rps / (c * mu)
    if rho >= 1.0:
        return 1.0
    a = lambda_rps / mu
    try:
        summation = sum((a ** n) / math.factorial(n) for n in range(c))
        last = (a ** c) / (math.factorial(c) * (1.0 - rho))
        return last / (summation + last)
    except (OverflowError, ZeroDivisionError):
        return float("nan")


def expected_queueing_delay(lambda_rps: float, mu: float, c: int) -> float:
    if c <= 0 or mu <= 0 or lambda_rps < 0:
        return float("nan")
    if lambda_rps >= c * mu:
        return float("inf")
    p_wait = erlang_c(lambda_rps, mu, c)
    return p_wait / (c * mu - lambda_rps)


def waiting_percentile_mmc(lambda_rps: float, mu: float, c: int, percentile: float) -> float:
    if c <= 0 or mu <= 0 or lambda_rps < 0:
        return float("nan")
    if not 0 < percentile < 1:
        return float("nan")
    if lambda_rps >= c * mu:
        return float("inf")
    pw = erlang_c(lambda_rps, mu, c)
    tail_prob = 1.0 - percentile
    if pw <= tail_prob:
        return 0.0
    return math.log(pw / tail_prob) / (c * mu - lambda_rps)


def recommend_replicas_slo_mmc(
    lambda_rps: float,
    mu: float,
    wq_allowed_s: float,
    min_replicas: int,
    max_replicas: int,
    current_replicas: int,
    queue_percentile: float = 0.95,
) -> int:
    if not all(valid_number(x) for x in [lambda_rps, mu, wq_allowed_s]):
        return current_replicas
    if lambda_rps <= 0 or mu <= 0 or wq_allowed_s < 0:
        return current_replicas
    for c in range(min_replicas, max_replicas + 1):
        wq_model_s = waiting_percentile_mmc(lambda_rps, mu, c, queue_percentile)
        if math.isfinite(wq_model_s) and wq_model_s <= wq_allowed_s:
            return c
    return max_replicas


def recommend_replicas_slo_ggc(
    lambda_rps: float,
    mu: float,
    k_variability: float,
    wq_allowed_s: float,
    min_replicas: int,
    max_replicas: int,
    current_replicas: int,
    queue_percentile: float = 0.95,
) -> int:
    if not all(valid_number(x) for x in [lambda_rps, mu, k_variability, wq_allowed_s]):
        return current_replicas
    if lambda_rps <= 0 or mu <= 0 or k_variability <= 0 or wq_allowed_s < 0:
        return current_replicas
    for c in range(min_replicas, max_replicas + 1):
        wq_tail_mmc_s = waiting_percentile_mmc(lambda_rps, mu, c, queue_percentile)
        wq_tail_ggc_s = k_variability * wq_tail_mmc_s
        if math.isfinite(wq_tail_ggc_s) and wq_tail_ggc_s <= wq_allowed_s:
            return c
    return max_replicas


def predict_tail_mmc_ms(
    lambda_rps: float,
    mu: float,
    replicas: int,
    service_time_s: float,
    queue_percentile: float,
) -> float:
    if replicas <= 0 or not valid_number(lambda_rps) or not valid_number(mu) or not valid_number(service_time_s):
        return float("nan")
    wq_s = waiting_percentile_mmc(lambda_rps, mu, replicas, queue_percentile)
    if not math.isfinite(wq_s):
        return float("inf") if wq_s == float("inf") else float("nan")
    return (service_time_s + wq_s) * 1000.0


def update_healthy_self_tail_history(
    history_ms: list[float],
    self_tail_ms: float,
    local_slo_ms: float,
    max_samples: int = 40,
) -> bool:
    if not valid_number(self_tail_ms) or self_tail_ms <= 0:
        return False
    if not valid_number(local_slo_ms) or local_slo_ms <= 0:
        return False
    if self_tail_ms > local_slo_ms:
        return False
    history_ms.append(float(self_tail_ms))
    if len(history_ms) > max_samples:
        del history_ms[: len(history_ms) - max_samples]
    return True


def healthy_p90_target_ms(history_ms: list[float]) -> float | None:
    return percentile(history_ms, 0.25)


def wait_for_next_loop(timeout_s: float) -> None:
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        time.sleep(min(0.5, deadline - time.time()))


def das_loop(
    monitor: Monitor,
    executor: Executor,
    deployment: str,
    interval: float,
    scale_up_cooldown: float,
    scale_down_cooldown: float,
    min_replicas: int,
    max_replicas: int,
) -> None:
    last_scale_up_time = 0.0
    last_scale_down_time = 0.0
    last_processing_time_update = 0.0
    learned_processing_time_s = None
    healthy_self_p90_history_ms: list[float] = []
    scale_down_ok_windows = 0

    service_time_update_interval = float(os.getenv("SERVICE_TIME_UPDATE_INTERVAL_SECONDS", "29"))
    service_time_alpha = float(os.getenv("SERVICE_TIME_EWMA_ALPHA", "0.8"))
    min_processing_time_s = float(os.getenv("MIN_PROCESSING_TIME_MS", "1")) / 1000.0
    k_variability = float(os.getenv("GGC_INITIAL_K", "1.0"))
    variability_update_interval = float(os.getenv("GGC_K_UPDATE_INTERVAL_SECONDS", "180"))
    variability_alpha = float(os.getenv("GGC_K_EWMA_ALPHA", "0.8"))
    variability_k_min = float(os.getenv("GGC_K_MIN", "0.5"))
    variability_k_max = float(os.getenv("GGC_K_MAX", "10.0"))
    last_variability_update = 0.0
    fixed_processing_time_s, configured_service_time_source = get_baseline_processing_time_s(deployment)

    if fixed_processing_time_s is not None:
        logging.info(
            "[BASELINE CONFIG] deployment=%s fixed_processing_time=%.2f ms",
            deployment,
            fixed_processing_time_s * 1000,
        )
    else:
        logging.info(
            "[BASELINE CONFIG] deployment=%s fixed_processing_time=AUTO",
            deployment,
        )
    logging.info(
        "Starting DAS for deployment '%s' [Interval: %.1fs | Up Cooldown: %.1fs, Down Cooldown: %.1fs]",
        deployment,
        interval,
        scale_up_cooldown,
        scale_down_cooldown,
    )

    queue_tail_label, queue_tail_quantile = ("P90", 0.90)

    while True:
        try:
            now = time.time()
            deployment_resources = monitor.get_deployment_resources(deployment)
            if deployment_resources.running_pods <= 0:
                logging.warning("No running pods found for deployment '%s'", deployment)
                result = executor.scale_by(
                    deployment,
                    delta=1,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                )
                logging.info("[RECOVERY SCALE UP] %s result=%s", deployment, result)
                last_scale_up_time = now
                wait_for_next_loop(interval)
                continue

            cpu_m = deployment_resources.cpu_m
            mem_mib = deployment_resources.mem_mib
            pods_count = deployment_resources.running_pods

            deployment_utilisation = monitor.get_deployment_utilisation(deployment)
            cpu_utilisation = deployment_utilisation.cpu_pct
            mem_utilisation = deployment_utilisation.mem_pct

            http_rpm_as_dst = monitor.get_http_rpm_as_dst(deployment)
            grpc_rpm_as_dst = monitor.get_grpc_rpm_as_dst(deployment)
            http_latency_avg_as_dst = monitor.get_http_latency_as_dst(deployment)
            grpc_latency_avg_as_dst = monitor.get_grpc_latency_as_dst(deployment)
            http_latency_p25_as_dst = monitor.get_http_latency_p25_as_dst(deployment)
            grpc_latency_p25_as_dst = monitor.get_grpc_latency_p25_as_dst(deployment)
            http_latency_p50_as_dst = monitor.get_http_latency_p50_as_dst(deployment)
            grpc_latency_p50_as_dst = monitor.get_grpc_latency_p50_as_dst(deployment)
            http_latency_p90_as_dst = monitor.get_http_latency_p90_as_dst(deployment)
            grpc_latency_p90_as_dst = monitor.get_grpc_latency_p90_as_dst(deployment)
            http_latency_p95_as_dst = monitor.get_http_latency_p95_as_dst(deployment)
            grpc_latency_p95_as_dst = monitor.get_grpc_latency_p95_as_dst(deployment)

            required_metrics = {
                "http_rpm_as_dst": http_rpm_as_dst,
                "http_latency_p25_as_dst": http_latency_p25_as_dst,
                "http_latency_p90_as_dst": http_latency_p90_as_dst,
                "cpu_utilisation": cpu_utilisation,
                "pods_count": pods_count,
            }
            invalid_metrics = {
                name: value
                for name, value in required_metrics.items()
                if not valid_number(value)
            }
            if invalid_metrics:
                logging.warning("Invalid metrics for %s: %s. Skip scaling loop iteration.", deployment, invalid_metrics)
                wait_for_next_loop(interval)
                continue

            lambda_rps = (http_rpm_as_dst + grpc_rpm_as_dst) / 60.0
            R_avg_ms = http_latency_avg_as_dst + grpc_latency_avg_as_dst
            R_p25_ms = http_latency_p25_as_dst + grpc_latency_p25_as_dst
            R_p50_ms = http_latency_p50_as_dst + grpc_latency_p50_as_dst
            R_p90_ms = http_latency_p90_as_dst + grpc_latency_p90_as_dst
            R_p95_ms = http_latency_p95_as_dst + grpc_latency_p95_as_dst

            slo_tail_label, slo_tail_quantile = normalize_latency_percentile(
                os.getenv("SLO_LATENCY_PERCENTILE"),
                "p95",
            )
            R_slo_ms = R_p95_ms if slo_tail_label == "P95" else R_p90_ms
            latency_slo_ms = get_configured_latency_slo_ms()

            R_avg_s = R_avg_ms / 1000.0
            R_p25_s = R_p25_ms / 1000.0
            R_p90_s = R_p90_ms / 1000.0
            R_slo_s = R_slo_ms / 1000.0

            if learned_processing_time_s is None:
                if fixed_processing_time_s is None:
                    learned_processing_time_s = max(min_processing_time_s, R_p25_s)
                    service_time_source = "startup_p25"
                else:
                    learned_processing_time_s = max(min_processing_time_s, fixed_processing_time_s)
                    service_time_source = configured_service_time_source
                last_processing_time_update = now
                logging.info(
                    "[SERVICE TIME INIT] service=%s S=%.2fms p25=%.2fms source=%s",
                    deployment,
                    learned_processing_time_s * 1000,
                    R_p25_s * 1000,
                    service_time_source,
                )
            else:
                elapsed_since_s_update = now - last_processing_time_update
                if (
                    elapsed_since_s_update >= service_time_update_interval
                    and valid_number(R_p25_s)
                    and R_p25_s > min_processing_time_s
                ):
                    old_s = learned_processing_time_s
                    learned_processing_time_s = (
                        service_time_alpha * learned_processing_time_s
                        + (1.0 - service_time_alpha) * R_p25_s
                    )
                    last_processing_time_update = now
                    service_time_source = "smoothed_p25_all_load"
                    logging.info(
                        "[SERVICE TIME UPDATE] service=%s old_S=%.2fms new_S=%.2fms p25=%.2fms alpha=%.2f source=%s",
                        deployment,
                        old_s * 1000,
                        learned_processing_time_s * 1000,
                        R_p25_s * 1000,
                        service_time_alpha,
                        service_time_source,
                    )
                else:
                    service_time_source = (
                        "cached_p25" if fixed_processing_time_s is None else "cached_configured_baseline"
                    )

            S_s = learned_processing_time_s
            mu = 1.0 / S_s if S_s > 0 else 0.0
            rho = lambda_rps / (pods_count * mu) if mu > 0 and pods_count > 0 else float("inf")

            if R_slo_ms <= latency_slo_ms:
                learned = update_healthy_self_tail_history(
                    history_ms=healthy_self_p90_history_ms,
                    self_tail_ms=R_slo_ms,
                    local_slo_ms=latency_slo_ms,
                )
                if learned:
                    logging.info(
                        "[HEALTHY LEARN] service=%s %s=%.2fms target_p25=%.2fms samples=%d",
                        deployment,
                        slo_tail_label,
                        R_slo_ms,
                        healthy_p90_target_ms(healthy_self_p90_history_ms) or float("nan"),
                        len(healthy_self_p90_history_ms),
                    )

            own_healthy_p90_target_ms = healthy_p90_target_ms(healthy_self_p90_history_ms)
            local_scale_down_target_ms = (
                min(latency_slo_ms, own_healthy_p90_target_ms)
                if own_healthy_p90_target_ms is not None and valid_number(own_healthy_p90_target_ms)
                else latency_slo_ms
            )

            if (
                now - last_variability_update >= variability_update_interval
                and mu > 0
                and valid_number(R_slo_s)
                and R_slo_s > 0
            ):
                observed_tail_excess_s = max(0.0, R_slo_s - S_s)
                wq_tail_mmc_current_s = waiting_percentile_mmc(lambda_rps, mu, pods_count, queue_tail_quantile)
                if math.isfinite(wq_tail_mmc_current_s) and wq_tail_mmc_current_s > 1e-9:
                    raw_k = observed_tail_excess_s / wq_tail_mmc_current_s
                    clipped_k = max(variability_k_min, min(variability_k_max, raw_k))
                    old_k = k_variability
                    k_variability = (
                        variability_alpha * k_variability
                        + (1.0 - variability_alpha) * clipped_k
                    )
                    last_variability_update = now
                    logging.info(
                        "[GGC K UPDATE] service=%s old_k=%.3f raw_k=%.3f clipped_k=%.3f new_k=%.3f",
                        deployment,
                        old_k,
                        raw_k,
                        clipped_k,
                        k_variability,
                    )

            effective_latency_target_ms = latency_slo_ms
            wq_allowed_s = max(0.001, (effective_latency_target_ms / 1000.0) - S_s)
            slo_recommended_mmc = recommend_replicas_slo_mmc(
                lambda_rps=lambda_rps,
                mu=mu,
                wq_allowed_s=wq_allowed_s,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                current_replicas=pods_count,
                queue_percentile=queue_tail_quantile,
            )
            slo_recommended = recommend_replicas_slo_ggc(
                lambda_rps=lambda_rps,
                mu=mu,
                k_variability=k_variability,
                wq_allowed_s=wq_allowed_s,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                current_replicas=pods_count,
                queue_percentile=queue_tail_quantile,
            )
            desired_replicas = max(slo_recommended_mmc, slo_recommended)
            desired_replicas = max(min_replicas, min(max_replicas, desired_replicas))

            p_wait_current = erlang_c(lambda_rps, mu, pods_count)
            wq_model_current_s = waiting_percentile_mmc(lambda_rps, mu, pods_count, queue_tail_quantile)
            wq_model_current_s_ggc = k_variability * wq_model_current_s if math.isfinite(wq_model_current_s) else wq_model_current_s

            logging.info(
                "\n"
                "==================== DAS STATE ====================\n"
                f"[Service] {deployment}\n"
                f"  λ (arrival rate)        : {lambda_rps:.2f} req/s\n"
                f"  Replicas (c)            : {pods_count}\n"
                f"  Capacity (c·μ)          : {(pods_count * mu):.2f} req/s\n"
                f"  {slo_tail_label} (observed)  : {R_slo_ms:.2f} ms\n"
                f"  Local SLO              : {latency_slo_ms:.2f} ms\n"
                f"  Effective target       : {effective_latency_target_ms:.2f} ms\n"
                f"  Processing time S      : {S_s * 1000:.2f} ms\n"
                f"  Variability factor k   : {k_variability:.3f}\n"
                f"  ρ (utilisation)        : {rho:.2f}\n"
                f"  Modelled {queue_tail_label} queue delay MMC: {wq_model_current_s * 1000:.2f} ms\n"
                f"  Modelled {queue_tail_label} queue delay GGC: {wq_model_current_s_ggc * 1000:.2f} ms\n"
                f"  SLO recommended MMC    : {slo_recommended_mmc}\n"
                f"  SLO recommended GGC    : {slo_recommended}\n"
                "===================================================\n"
            )

            logging.info(
                build_deployment_monitoring_log(
                    deployment=deployment,
                    cpu_m=cpu_m,
                    mem_mib=mem_mib,
                    pods_count=pods_count,
                    cpu_utilisation=cpu_utilisation,
                    mem_utilisation=mem_utilisation,
                    http_rpm_as_dst=http_rpm_as_dst,
                    grpc_rpm_as_dst=grpc_rpm_as_dst,
                    http_latency_p50_as_dst=http_latency_p50_as_dst,
                    grpc_latency_p50_as_dst=grpc_latency_p50_as_dst,
                    http_latency_p90_as_dst=http_latency_p90_as_dst,
                    grpc_latency_p90_as_dst=grpc_latency_p90_as_dst,
                    http_latency_p95_as_dst=http_latency_p95_as_dst,
                    grpc_latency_p95_as_dst=grpc_latency_p95_as_dst,
                    http_rpm_as_src=0.0,
                    grpc_rpm_as_src=0.0,
                    http_latency_p50_as_src=0.0,
                    grpc_latency_p50_as_src=0.0,
                    http_latency_p90_as_src=0.0,
                    grpc_latency_p90_as_src=0.0,
                    http_latency_p95_as_src=0.0,
                    grpc_latency_p95_as_src=0.0,
                    http_rpm_mesh_as_dst=None,
                    grpc_rpm_mesh_as_dst=None,
                    http_latency_mesh_avg_as_dst=None,
                    grpc_latency_mesh_avg_as_dst=None,
                    http_latency_p95_mesh_as_dst=None,
                    grpc_latency_p95_mesh_as_dst=None,
                    http_latency_p90_mesh_as_dst=None,
                    grpc_latency_p90_mesh_as_dst=None,
                    http_rpm_mesh_as_src=None,
                    grpc_rpm_mesh_as_src=None,
                    http_latency_mesh_avg_as_src=None,
                    grpc_latency_mesh_avg_as_src=None,
                    http_latency_p95_mesh_as_src=None,
                    grpc_latency_p95_mesh_as_src=None,
                    http_latency_p90_mesh_as_src=None,
                    grpc_latency_p90_mesh_as_src=None,
                    upstreams=None,
                    downstreams=None,
                    selected_tail_label=queue_tail_label,
                )
            )

            if desired_replicas > pods_count:
                if now - last_scale_up_time < scale_up_cooldown:
                    logging.info(
                        "[COOLDOWN HOLD] Scale-Up request throttled. Elapsed: %.1fs | Required: %.1fs",
                        now - last_scale_up_time,
                        scale_up_cooldown,
                    )
                else:
                    result = executor.scale_by(
                        deployment,
                        delta=desired_replicas - pods_count,
                        min_replicas=min_replicas,
                        max_replicas=max_replicas,
                    )
                    last_scale_up_time = now
                    scale_down_ok_windows = 0
                    logging.info(
                        "[SCALE UP ACTION] %s scaling to %d replicas. Result=%s",
                        deployment,
                        desired_replicas,
                        result,
                    )
            else:
                candidate_replicas = max(min_replicas, pods_count - 1)
                predicted_tail_down_ms = predict_tail_mmc_ms(
                    lambda_rps,
                    mu,
                    candidate_replicas,
                    S_s,
                    queue_tail_quantile,
                )
                scale_down_safe = (
                    candidate_replicas >= min_replicas
                    and math.isfinite(predicted_tail_down_ms)
                    and predicted_tail_down_ms <= local_scale_down_target_ms
                )
                if scale_down_safe:
                    scale_down_ok_windows += 1
                else:
                    scale_down_ok_windows = 0
                required_windows = int(os.getenv("SCALE_DOWN_MIN_WINDOWS", "2"))
                logging.info(
                    "[SCALE DOWN CHECK] candidate=%d predicted_%s=%.2fms local_target=%.2fms ok_windows=%d required_windows=%d",
                    candidate_replicas,
                    queue_tail_label.lower(),
                    predicted_tail_down_ms,
                    local_scale_down_target_ms,
                    scale_down_ok_windows,
                    required_windows,
                )
                if scale_down_safe and scale_down_ok_windows >= required_windows:
                    if now - last_scale_down_time < scale_down_cooldown:
                        logging.info(
                            "[COOLDOWN HOLD] Scale-Down request throttled. Elapsed: %.1fs | Required: %.1fs",
                            now - last_scale_down_time,
                            scale_down_cooldown,
                        )
                    else:
                        result = executor.scale_by(
                            deployment,
                            delta=-1,
                            min_replicas=min_replicas,
                            max_replicas=max_replicas,
                        )
                        last_scale_down_time = now
                        scale_down_ok_windows = 0
                        logging.info(
                            "[SCALE DOWN ACTION] %s scaling delta=-1 executed. Result=%s",
                            deployment,
                            result,
                        )

        except Exception as exc:
            logging.exception("[ERROR] %s", exc)
        wait_for_next_loop(interval)


def main() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    interval = float(os.getenv("INTERVAL", "15"))
    scale_up_cooldown = float(os.getenv("SCALE_UP_COOLDOWN_SECONDS", "30"))
    scale_down_cooldown = float(os.getenv("SCALE_DOWN_COOLDOWN_SECONDS", "180"))
    namespace = os.getenv("NAMESPACE", "default")
    deployment = os.getenv("TARGET_DEPLOYMENT", "productpage-v1")
    prom_url = os.getenv("PROM_URL", "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query")
    min_replicas = int(os.getenv("MIN_REPLICAS", "1"))
    max_replicas = int(os.getenv("MAX_REPLICAS", "10"))

    monitor = Monitor(namespace=namespace, prom_url=prom_url)
    executor = Executor(namespace=namespace)

    das_loop(
        monitor=monitor,
        executor=executor,
        deployment=deployment,
        interval=interval,
        scale_up_cooldown=scale_up_cooldown,
        scale_down_cooldown=scale_down_cooldown,
        min_replicas=min_replicas,
        max_replicas=max_replicas,
    )


if __name__ == "__main__":
    main()
