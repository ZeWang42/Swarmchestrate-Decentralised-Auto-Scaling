from __future__ import annotations

import logging
import math
import os
import time

from kubernetes import config

from execution import Executor
from monitoring import Monitor


APP_NAME = os.getenv("APP_NAME", "onlineboutique").strip().lower()
ROOT_SERVICE = os.getenv(
    "ROOT_SERVICE",
    "productpage-v1" if APP_NAME == "bookinfo" else "frontend",
).strip()

P25_FROM_P50_FACTOR = 2.0 / 3.0
LOG_FILE = os.getenv("LOG_FILE", "/tmp/customdas.log")


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

BASELINE_LOCAL_SLO_MS_BY_APP: dict[str, dict[str, float | None]] = {
    "onlineboutique": {
        "frontend": 500,
        "cartservice": 20,
        "checkoutservice": 250,
        "productcatalogservice": 20,
        "recommendationservice": 50,
        "currencyservice": 20,
        "adservice": 20,
        "emailservice": 20,
        "paymentservice": 20,
        "shippingservice": 20,
        "redis-cart": 20,
    },
    "bookinfo": {
        "productpage-v1": 200,
        "details-v1": 20,
        "ratings-v1": 20,
        "reviews-v1": 20,
        "reviews-v2": 20,
        "reviews-v3": 20,
    },
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def configure_logging() -> None:
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


configure_logging()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def valid_number(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value >= 0


def percentile(values: list[float], quantile: float) -> float | None:
    clean = sorted(float(value) for value in values if valid_number(value) and value > 0)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]

    quantile = max(0.0, min(1.0, quantile))
    position = (len(clean) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return clean[lower]

    return clean[lower] * (upper - position) + clean[upper] * (position - lower)


def normalize_latency_percentile(
    raw_value: str | None,
    default: str = "p95",
) -> tuple[str, float]:
    value = (raw_value or default).strip().lower().replace(" ", "")
    aliases = {
        "p25": ("P25", 0.25),
        "25": ("P25", 0.25),
        "0.25": ("P25", 0.25),
        "p50": ("P50", 0.50),
        "50": ("P50", 0.50),
        "0.50": ("P50", 0.50),
        "0.5": ("P50", 0.50),
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
            "Unsupported latency percentile %r; using %s",
            raw_value,
            default,
        )
        return aliases[default]

    return aliases[value]



def get_baseline_processing_time_s(deployment: str) -> float | None:
    baseline_ms = BASELINE_PROCESSING_TIME_MS_BY_APP.get(APP_NAME, {}).get(deployment)

    if baseline_ms is None:
        for app_table in BASELINE_PROCESSING_TIME_MS_BY_APP.values():
            if deployment in app_table:
                baseline_ms = app_table[deployment]
                break

    if baseline_ms is None:
        return None

    return (float(baseline_ms) * P25_FROM_P50_FACTOR) / 1000.0


def get_configured_local_slo_ms(
    app_name: str,
    deployment: str,
    *,
    allow_env_override: bool,
) -> float:
    """Return the configured latency SLO for one deployment.

    Environment overrides are allowed only for the root/frontend service.
    Non-root services use the per-application baseline table.
    """
    if allow_env_override:
        for env_name in (
            "LATENCY_SLO_MS",
            "SLO_MS",
            "SLO_LATENCY_MS",
            "FRONTEND_HEALTHY_LATENCY_MS",
        ):
            raw_value = os.getenv(env_name)
            if raw_value is None or not raw_value.strip():
                continue
            try:
                parsed_value = float(raw_value)
                if parsed_value > 0:
                    return parsed_value
            except ValueError:
                logging.warning("Ignoring invalid %s=%r", env_name, raw_value)

    configured_slo_ms = BASELINE_LOCAL_SLO_MS_BY_APP.get(app_name, {}).get(deployment)
    if configured_slo_ms is None:
        configured_slo_ms = BASELINE_LOCAL_SLO_MS_BY_APP.get(app_name, {}).get("default")

    return float(configured_slo_ms) if configured_slo_ms is not None else 500.0


def add_local_slo_candidate(
    history_ms: list[float],
    local_slo_candidate_ms: float,
    frontend_slo_ms: float,
    max_samples: int = 40,
) -> bool:
    if not valid_number(local_slo_candidate_ms) or local_slo_candidate_ms <= 0:
        return False
    if not valid_number(frontend_slo_ms) or frontend_slo_ms <= 0:
        return False

    # A local service budget should never exceed the end-to-end frontend budget.
    history_ms.append(min(float(local_slo_candidate_ms), float(frontend_slo_ms)))

    if len(history_ms) > max_samples:
        del history_ms[: len(history_ms) - max_samples]

    return True


def learned_local_slo_ms(history_ms: list[float]) -> float | None:
    return percentile(history_ms, 0.25)


def wait_for_next_loop(timeout_s: float) -> None:
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        time.sleep(min(0.5, deadline - time.time()))


# ---------------------------------------------------------------------------
# Queueing model
# ---------------------------------------------------------------------------


def erlang_c(arrival_rate_rps: float, service_rate_rps: float, replicas: int) -> float:
    if not valid_number(arrival_rate_rps) or not valid_number(service_rate_rps):
        return float("nan")
    if replicas <= 0 or service_rate_rps <= 0:
        return float("nan")

    utilisation = arrival_rate_rps / (replicas * service_rate_rps)
    if utilisation >= 1.0:
        return 1.0

    offered_load = arrival_rate_rps / service_rate_rps

    try:
        denominator_sum = sum(
            (offered_load**n) / math.factorial(n)
            for n in range(replicas)
        )
        waiting_term = (
            offered_load**replicas
            / (math.factorial(replicas) * (1.0 - utilisation))
        )
        return waiting_term / (denominator_sum + waiting_term)
    except (OverflowError, ZeroDivisionError):
        return float("nan")


def waiting_percentile_mmc(
    arrival_rate_rps: float,
    service_rate_rps: float,
    replicas: int,
    queue_percentile: float,
) -> float:
    if replicas <= 0 or service_rate_rps <= 0 or arrival_rate_rps < 0:
        return float("nan")
    if not 0 < queue_percentile < 1:
        return float("nan")
    if arrival_rate_rps >= replicas * service_rate_rps:
        return float("inf")

    probability_wait = erlang_c(arrival_rate_rps, service_rate_rps, replicas)
    tail_probability = 1.0 - queue_percentile

    if probability_wait <= tail_probability:
        return 0.0

    return math.log(probability_wait / tail_probability) / (
        replicas * service_rate_rps - arrival_rate_rps
    )


def recommend_replicas_mmc(
    arrival_rate_rps: float,
    service_rate_rps: float,
    queue_delay_budget_s: float,
    min_replicas: int,
    max_replicas: int,
    current_replicas: int,
    queue_percentile: float,
) -> int:
    if not all(
        valid_number(value)
        for value in (arrival_rate_rps, service_rate_rps, queue_delay_budget_s)
    ):
        return current_replicas

    if arrival_rate_rps <= 0 or service_rate_rps <= 0 or queue_delay_budget_s < 0:
        return current_replicas

    for replicas in range(min_replicas, max_replicas + 1):
        predicted_queue_delay_s = waiting_percentile_mmc(
            arrival_rate_rps,
            service_rate_rps,
            replicas,
            queue_percentile,
        )
        if (
            math.isfinite(predicted_queue_delay_s)
            and predicted_queue_delay_s <= queue_delay_budget_s
        ):
            return replicas

    return max_replicas


def recommend_replicas_ggc(
    arrival_rate_rps: float,
    service_rate_rps: float,
    variability_factor: float,
    queue_delay_budget_s: float,
    min_replicas: int,
    max_replicas: int,
    current_replicas: int,
    queue_percentile: float,
) -> int:
    if not all(
        valid_number(value)
        for value in (
            arrival_rate_rps,
            service_rate_rps,
            variability_factor,
            queue_delay_budget_s,
        )
    ):
        return current_replicas

    if (
        arrival_rate_rps <= 0
        or service_rate_rps <= 0
        or variability_factor <= 0
        or queue_delay_budget_s < 0
    ):
        return current_replicas

    for replicas in range(min_replicas, max_replicas + 1):
        predicted_queue_delay_mmc_s = waiting_percentile_mmc(
            arrival_rate_rps,
            service_rate_rps,
            replicas,
            queue_percentile,
        )
        predicted_queue_delay_ggc_s = variability_factor * predicted_queue_delay_mmc_s

        if (
            math.isfinite(predicted_queue_delay_ggc_s)
            and predicted_queue_delay_ggc_s <= queue_delay_budget_s
        ):
            return replicas

    return max_replicas


def predict_local_latency_mmc_ms(
    arrival_rate_rps: float,
    service_rate_rps: float,
    replicas: int,
    processing_time_s: float,
    queue_percentile: float,
) -> float:
    if (
        replicas <= 0
        or not valid_number(arrival_rate_rps)
        or not valid_number(service_rate_rps)
        or not valid_number(processing_time_s)
    ):
        return float("nan")

    predicted_queue_delay_s = waiting_percentile_mmc(
        arrival_rate_rps,
        service_rate_rps,
        replicas,
        queue_percentile,
    )

    if not math.isfinite(predicted_queue_delay_s):
        return float("inf") if predicted_queue_delay_s == float("inf") else float("nan")

    return (processing_time_s + predicted_queue_delay_s) * 1000.0


# ---------------------------------------------------------------------------
# Monitoring helpers
# ---------------------------------------------------------------------------



def get_observed_local_latency_ms(
    monitor: Monitor,
    deployment: str,
    percentile_label: str,
) -> float | None:
    """Fetch only the configured local latency percentile for this loop."""
    getters = {
        "P25": (
            monitor.get_http_latency_p25_as_dst,
            monitor.get_grpc_latency_p25_as_dst,
        ),
        "P50": (
            monitor.get_http_latency_p50_as_dst,
            monitor.get_grpc_latency_p50_as_dst,
        ),
        "P90": (
            monitor.get_http_latency_p90_as_dst,
            monitor.get_grpc_latency_p90_as_dst,
        ),
        "P95": (
            monitor.get_http_latency_p95_as_dst,
            monitor.get_grpc_latency_p95_as_dst,
        ),
    }

    http_getter, grpc_getter = getters.get(percentile_label, getters["P95"])
    http_latency_ms = http_getter(deployment)
    grpc_latency_ms = grpc_getter(deployment)

    if not valid_number(http_latency_ms) or not valid_number(grpc_latency_ms):
        return None

    return float(http_latency_ms) + float(grpc_latency_ms)



def get_observed_frontend_latency_ms(
    monitor: Monitor,
    percentile_label: str,
) -> float | None:
    getters = {
        "P25": (
            monitor.get_http_latency_p25_as_dst,
            monitor.get_http_latency_p25_as_src,
        ),
        "P50": (
            monitor.get_http_latency_p50_as_dst,
            monitor.get_http_latency_p50_as_src,
        ),
        "P90": (
            monitor.get_http_latency_p90_as_dst,
            monitor.get_http_latency_p90_as_src,
        ),
        "P95": (
            monitor.get_http_latency_p95_as_dst,
            monitor.get_http_latency_p95_as_src,
        ),
    }

    dst_getter, src_getter = getters.get(percentile_label, getters["P95"])

    observed_frontend_latency_ms = dst_getter(ROOT_SERVICE)
    if not valid_number(observed_frontend_latency_ms):
        observed_frontend_latency_ms = src_getter(ROOT_SERVICE)

    return (
        float(observed_frontend_latency_ms)
        if valid_number(observed_frontend_latency_ms)
        else None
    )


def format_optional_ms(value: float | None) -> str:
    return "N/A" if value is None or not valid_number(value) else f"{value:.2f}ms"


# ---------------------------------------------------------------------------
# DAS control loop
# ---------------------------------------------------------------------------


def das_loop(
    monitor: Monitor,
    executor: Executor,
    deployment: str,
    interval_s: float,
    scale_down_cooldown_s: float,
    min_replicas: int,
    max_replicas: int,
) -> None:
    last_scale_down_time = 0.0
    last_processing_time_update = 0.0
    last_variability_update = 0.0

    processing_time_s: float | None = None
    adaptive_local_slo_history_ms: list[float] = []
    scale_down_safe_windows = 0

    local_slo_mode = os.getenv("LATENCY_SLO_MODE", "adaptive").strip().lower()
    if local_slo_mode not in {"adaptive", "fixed"}:
        logging.warning(
            "Unsupported LATENCY_SLO_MODE=%r; using adaptive",
            local_slo_mode,
        )
        local_slo_mode = "adaptive"

    queue_model = os.getenv("QUEUE_MODEL", "mmc").strip().lower()
    if queue_model not in {"mmc", "ggc"}:
        logging.warning("Unsupported QUEUE_MODEL=%r; using mmc", queue_model)
        queue_model = "mmc"

    local_latency_label, _ = normalize_latency_percentile(
        os.getenv("SLO_LATENCY_PERCENTILE"),
        "p95",
    )
    _, queue_percentile = normalize_latency_percentile(
        os.getenv("QUEUE_MODEL_PERCENTILE"),
        "p95",
    )

    processing_time_update_interval_s = float(
        os.getenv("SERVICE_TIME_UPDATE_INTERVAL_SECONDS", "29")
    )
    processing_time_ewma_alpha = float(os.getenv("SERVICE_TIME_EWMA_ALPHA", "0.8"))
    min_processing_time_s = float(os.getenv("MIN_PROCESSING_TIME_MS", "1")) / 1000.0
    baseline_processing_time_s = get_baseline_processing_time_s(deployment)

    variability_factor = float(os.getenv("GGC_INITIAL_K", "1.0"))
    variability_update_interval_s = float(
        os.getenv("GGC_K_UPDATE_INTERVAL_SECONDS", "180")
    )
    variability_ewma_alpha = float(os.getenv("GGC_K_EWMA_ALPHA", "0.8"))
    variability_min = float(os.getenv("GGC_K_MIN", "0.5"))
    variability_max = float(os.getenv("GGC_K_MAX", "10.0"))

    required_scale_down_windows = int(os.getenv("SCALE_DOWN_MIN_WINDOWS", "2"))

    is_frontend_service = deployment == ROOT_SERVICE
    frontend_slo_ms = get_configured_local_slo_ms(
        APP_NAME,
        ROOT_SERVICE,
        allow_env_override=True,
    )
    configured_local_slo_ms = get_configured_local_slo_ms(
        APP_NAME,
        deployment,
        allow_env_override=is_frontend_service,
    )

    # The root/frontend defines the end-to-end SLO, so it always stays fixed.
    effective_local_slo_mode = "fixed" if is_frontend_service else local_slo_mode

    logging.info(
        "Starting DAS service=%s mode=%s model=%s interval=%.1fs down_cooldown=%.1fs",
        deployment,
        effective_local_slo_mode,
        queue_model,
        interval_s,
        scale_down_cooldown_s,
    )

    while True:
        try:
            now = time.time()

            # -----------------------------------------------------------------
            # Observe current deployment state
            # -----------------------------------------------------------------
            deployment_resources = monitor.get_deployment_resources(deployment)
            current_replicas = deployment_resources.running_pods

            if current_replicas <= 0:
                result = executor.scale_by(
                    deployment,
                    delta=1,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                )
                logging.warning(
                    "[RECOVERY] service=%s replicas=0 scale_up_by=1 result=%s",
                    deployment,
                    result,
                )
                wait_for_next_loop(interval_s)
                continue

            utilisation = monitor.get_deployment_utilisation(deployment)
            cpu_utilisation_pct = utilisation.cpu_pct

            http_rpm = monitor.get_http_rpm_as_dst(deployment)
            grpc_rpm = monitor.get_grpc_rpm_as_dst(deployment)

            # Fetch only the latency percentile selected by SLO_LATENCY_PERCENTILE.
            observed_local_latency_ms = get_observed_local_latency_ms(
                monitor,
                deployment,
                local_latency_label,
            )

            # P25 is the processing-time estimator. Reuse the selected metric when
            # SLO_LATENCY_PERCENTILE=P25; otherwise fetch P25 separately.
            if local_latency_label == "P25":
                observed_local_p25_ms = observed_local_latency_ms
            else:
                observed_local_p25_ms = get_observed_local_latency_ms(
                    monitor,
                    deployment,
                    "P25",
                )

            required_metrics = {
                "http_rpm": http_rpm,
                "grpc_rpm": grpc_rpm,
                "cpu_utilisation_pct": cpu_utilisation_pct,
                f"local_latency_{local_latency_label.lower()}_ms": observed_local_latency_ms,
                "local_latency_p25_ms": observed_local_p25_ms,
            }
            invalid_metrics = {
                name: value
                for name, value in required_metrics.items()
                if not valid_number(value)
            }

            if invalid_metrics:
                logging.warning(
                    "[SKIP] service=%s invalid_metrics=%s",
                    deployment,
                    invalid_metrics,
                )
                wait_for_next_loop(interval_s)
                continue

            arrival_rate_rps = (http_rpm + grpc_rpm) / 60.0

            # Fetch frontend latency for both adaptive learning and compact logging.
            if is_frontend_service:
                observed_frontend_latency_ms = observed_local_latency_ms
            else:
                observed_frontend_latency_ms = get_observed_frontend_latency_ms(
                    monitor,
                    local_latency_label,
                )

            # -----------------------------------------------------------------
            # Determine the local SLO
            # -----------------------------------------------------------------
            local_slo_ms = configured_local_slo_ms

            if effective_local_slo_mode == "adaptive":
                learned_slo_ms = learned_local_slo_ms(adaptive_local_slo_history_ms)
                if learned_slo_ms is not None:
                    local_slo_ms = learned_slo_ms

                # Learn only while frontend latency is comfortably below its SLO.
                if (
                    valid_number(observed_frontend_latency_ms)
                    and observed_frontend_latency_ms > 0
                    and observed_frontend_latency_ms < 0.7 * frontend_slo_ms
                ):
                    local_slo_candidate_ms = (observed_local_latency_ms)

                    if add_local_slo_candidate(
                        adaptive_local_slo_history_ms,
                        local_slo_candidate_ms,
                        frontend_slo_ms,
                    ):
                        learned_slo_ms = learned_local_slo_ms(
                            adaptive_local_slo_history_ms
                        )
                        if learned_slo_ms is not None:
                            local_slo_ms = learned_slo_ms

            # -----------------------------------------------------------------
            # Estimate processing time and service rate
            # -----------------------------------------------------------------
            observed_local_p25_s = observed_local_p25_ms / 1000.0

            if processing_time_s is None:
                if baseline_processing_time_s is None:
                    processing_time_s = max(
                        min_processing_time_s,
                        observed_local_p25_s,
                    )
                else:
                    processing_time_s = max(
                        min_processing_time_s,
                        baseline_processing_time_s,
                    )
                last_processing_time_update = now

            elif (
                now - last_processing_time_update >= processing_time_update_interval_s
                and valid_number(observed_local_p25_s)
                and observed_local_p25_s > min_processing_time_s
            ):
                processing_time_s = (
                    processing_time_ewma_alpha * processing_time_s
                    + (1.0 - processing_time_ewma_alpha) * observed_local_p25_s
                )
                last_processing_time_update = now

            service_rate_rps = 1.0 / processing_time_s if processing_time_s > 0 else 0.0

            # -----------------------------------------------------------------
            # Optional G/G/c variability update
            # -----------------------------------------------------------------
            if (
                queue_model == "ggc"
                and now - last_variability_update >= variability_update_interval_s
                and service_rate_rps > 0
            ):
                observed_local_latency_s = observed_local_latency_ms / 1000.0
                observed_queue_delay_s = max(
                    0.0,
                    observed_local_latency_s - processing_time_s,
                )
                predicted_queue_delay_mmc_s = waiting_percentile_mmc(
                    arrival_rate_rps,
                    service_rate_rps,
                    current_replicas,
                    queue_percentile,
                )

                if (
                    math.isfinite(predicted_queue_delay_mmc_s)
                    and predicted_queue_delay_mmc_s > 1e-9
                ):
                    raw_variability_factor = (
                        observed_queue_delay_s / predicted_queue_delay_mmc_s
                    )
                    clipped_variability_factor = max(
                        variability_min,
                        min(variability_max, raw_variability_factor),
                    )
                    variability_factor = (
                        variability_ewma_alpha * variability_factor
                        + (1.0 - variability_ewma_alpha)
                        * clipped_variability_factor
                    )
                    last_variability_update = now

            # -----------------------------------------------------------------
            # Recommend replicas from the local SLO
            # -----------------------------------------------------------------
            queue_delay_budget_s = max(
                0.001,
                (local_slo_ms / 1000.0) - processing_time_s,
            )

            if queue_model == "ggc":
                desired_replicas = recommend_replicas_ggc(
                    arrival_rate_rps=arrival_rate_rps,
                    service_rate_rps=service_rate_rps,
                    variability_factor=variability_factor,
                    queue_delay_budget_s=queue_delay_budget_s,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                    current_replicas=current_replicas,
                    queue_percentile=queue_percentile,
                )
            else:
                desired_replicas = recommend_replicas_mmc(
                    arrival_rate_rps=arrival_rate_rps,
                    service_rate_rps=service_rate_rps,
                    queue_delay_budget_s=queue_delay_budget_s,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                    current_replicas=current_replicas,
                    queue_percentile=queue_percentile,
                )

            desired_replicas = max(
                min_replicas,
                min(max_replicas, desired_replicas),
            )

            logging.info(
                "[STATE] service=%s lambda=%.2f req/s replicas=%d desired=%d "
                "cpu=%.1f%% local_latency_%s=%.2fms local_slo=%.2fms "
                "frontend_latency_%s=%s frontend_slo=%.2fms processing_time=%.2fms",
                deployment,
                arrival_rate_rps,
                current_replicas,
                desired_replicas,
                cpu_utilisation_pct,
                local_latency_label.lower(),
                observed_local_latency_ms,
                local_slo_ms,
                local_latency_label.lower(),
                format_optional_ms(observed_frontend_latency_ms),
                frontend_slo_ms,
                processing_time_s * 1000.0,
            )

            # -----------------------------------------------------------------
            # Scale up immediately when the model requires more replicas
            # -----------------------------------------------------------------
            if desired_replicas > current_replicas:
                result = executor.scale_by(
                    deployment,
                    delta=desired_replicas - current_replicas,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                )
                scale_down_safe_windows = 0
                logging.info(
                    "[SCALE UP] service=%s from=%d to=%d result=%s",
                    deployment,
                    current_replicas,
                    desired_replicas,
                    result,
                )

            # -----------------------------------------------------------------
            # Scale down one replica at a time, with safety windows + cooldown
            # -----------------------------------------------------------------
            elif desired_replicas < current_replicas:
                candidate_replicas = max(min_replicas, current_replicas - 1)
                predicted_local_latency_ms = predict_local_latency_mmc_ms(
                    arrival_rate_rps,
                    service_rate_rps,
                    candidate_replicas,
                    processing_time_s,
                    queue_percentile,
                )

                scale_down_safe = (
                    candidate_replicas >= min_replicas
                    and math.isfinite(predicted_local_latency_ms)
                    and predicted_local_latency_ms <= local_slo_ms
                )

                if scale_down_safe:
                    scale_down_safe_windows += 1
                else:
                    scale_down_safe_windows = 0

                cooldown_finished = (
                    now - last_scale_down_time >= scale_down_cooldown_s
                )

                if (
                    scale_down_safe
                    and scale_down_safe_windows >= required_scale_down_windows
                    and cooldown_finished
                ):
                    result = executor.scale_by(
                        deployment,
                        delta=-1,
                        min_replicas=min_replicas,
                        max_replicas=max_replicas,
                    )
                    last_scale_down_time = now
                    scale_down_safe_windows = 0
                    logging.info(
                        "[SCALE DOWN] service=%s from=%d to=%d result=%s",
                        deployment,
                        current_replicas,
                        candidate_replicas,
                        result,
                    )

            else:
                scale_down_safe_windows = 0

        except Exception as exc:
            logging.exception("[ERROR] service=%s error=%s", deployment, exc)

        wait_for_next_loop(interval_s)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    interval_s = float(os.getenv("INTERVAL", "15"))
    scale_down_cooldown_s = float(os.getenv("COOLDOWN_SECONDS", "120"))
    namespace = os.getenv("NAMESPACE", "default")
    deployment = os.getenv("TARGET_DEPLOYMENT", "productpage-v1")
    prom_url = os.getenv(
        "PROM_URL",
        "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    )
    min_replicas = int(os.getenv("MIN_REPLICAS", "1"))
    max_replicas = int(os.getenv("MAX_REPLICAS", "10"))

    monitor = Monitor(namespace=namespace, prom_url=prom_url)
    executor = Executor(namespace=namespace)

    das_loop(
        monitor=monitor,
        executor=executor,
        deployment=deployment,
        interval_s=interval_s,
        scale_down_cooldown_s=scale_down_cooldown_s,
        min_replicas=min_replicas,
        max_replicas=max_replicas,
    )


if __name__ == "__main__":
    main()
