from __future__ import annotations

import logging
import os
import time
import threading
import math
import random
from random import uniform
from typing import Any  # Fixed: Explicit import to prevent NameError syntax crashes

from kubernetes import config

from monitoring import Monitor
from execution import Executor
from p2pAgent import P2PAgent
from queue_das_logging import build_deployment_monitoring_log


# Application/root-service configuration.
# These values are injected by the autoscaler server template via env vars:
#   APP_NAME=bookinfo|onlineboutique
#   ROOT_SERVICE=productpage-v1|frontend
# ROOT_SERVICE takes precedence so the same image can be reused for different apps.
APP_NAME = os.getenv("APP_NAME", "onlineboutique").strip().lower()
ROOT_SERVICE = os.getenv(
    "ROOT_SERVICE",
    "productpage-v1" if APP_NAME == "bookinfo" else "frontend",
).strip()
ROOT_SERVICES = {ROOT_SERVICE} if ROOT_SERVICE else {"frontend"}

EXTERNAL_UPSTREAMS = {"gateway", "istio-ingressgateway", "unknown", ""}

# Processing-time model convention.
# The calibrated baseline table below stores the previously measured low-load P50
# latency. For the queueing service time S, use a P25-like processing-time proxy:
#     S_base = (2 / 3) * P50_base
# Runtime service-time updates also use the live P25 latency, not P50.
P25_FROM_P50_FACTOR = 2.0 / 3.0


# Calibrated baseline processing times in milliseconds.
# These values were estimated from low-load observations and are used as the
# fixed service time S in the queueing model. They deliberately avoid subtracting
# downstream latency because the true call structure may be serial, parallel,
# async, cached, retried, or partially overlapped.
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

# Backward-compatible merged lookup. This prevents one app's baseline table from
# overwriting the other, while still allowing APP_NAME to choose a preferred table.
BASELINE_PROCESSING_TIME_MS: dict[str, float | None] = {
    service: value
    for app_table in BASELINE_PROCESSING_TIME_MS_BY_APP.values()
    for service, value in app_table.items()
}

# Preferred lookup for the selected application. Unknown APP_NAME falls back to
# the merged lookup above.
SELECTED_APP_BASELINE_PROCESSING_TIME_MS: dict[str, float | None] = (
    BASELINE_PROCESSING_TIME_MS_BY_APP.get(APP_NAME, {})
)


def get_baseline_processing_time_s(deployment: str) -> tuple[float | None, str]:
    """Return baseline processing time in seconds.

    The baseline table stores low-load P50-like latency values. For this version
    of DAS, the queueing model uses a P25-like processing time proxy:

        S_base = (2 / 3) * P50_base

    No PROCESSING_TIME_MS environment-variable override is used here; the
    processing-time policy is fixed in code for reproducible experiments.
    """
    baseline_ms = SELECTED_APP_BASELINE_PROCESSING_TIME_MS.get(deployment)
    if baseline_ms is None:
        baseline_ms = BASELINE_PROCESSING_TIME_MS.get(deployment)

    if baseline_ms is not None:
        processing_ms = float(baseline_ms) * P25_FROM_P50_FACTOR
        return processing_ms / 1000.0, f"calibrated_p25_from_p50_table_{APP_NAME}"

    return None, "runtime_fallback_p25"





def normalize_latency_percentile(raw: str | None, default: str = "p95") -> tuple[str, float]:
    """Return a normalized percentile label and quantile for latency SLO logic.

    Accepted values include p90, 90, 0.90, p95, 95, and 0.95.
    """
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


def get_configured_latency_slo_ms(node_type: str) -> float:
    """Read the latency SLO from env vars.

    Preferred names:
      - LATENCY_SLO_MS / SLO_MS / SLO_LATENCY_MS for normal/root nodes
      - LATENCY_SLO_MS_LEAF_MS / SLO_LEAF_MS for leaf nodes
    """
    default_root_slo = os.getenv("SLO_MS", os.getenv("SLO_LATENCY_MS", "400"))
    latency_slo_ms = float(os.getenv("LATENCY_SLO_MS", default_root_slo))
    if node_type == "leaf":
        default_leaf_slo = os.getenv("SLO_LEAF_MS", "10")
        latency_slo_ms = float(os.getenv("LATENCY_SLO_MS_LEAF_MS", default_leaf_slo))
    return latency_slo_ms


LOG_FILE = os.getenv("LOG_FILE", "/tmp/customdas.log")
ENABLE_COLOURED_LOGS = os.getenv("ENABLE_COLOURED_LOGS", "1").strip().lower() not in {"0", "false", "no", "off"}

ANSI_RESET = "\033[0m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"
ANSI_GREEN = "\033[32m"
ANSI_CYAN = "\033[36m"


def colour_text(text: str, colour: str) -> str:
    """Colour selected text/table rows only when console colouring is enabled."""
    if not ENABLE_COLOURED_LOGS:
        return text
    return f"{colour}{text}{ANSI_RESET}"


class ConsoleColourFormatter(logging.Formatter):
    """Colour high-level operational action log lines in the console only."""

    ACTION_COLOURS = (
        ("[BOTTLENECK DETECTED]", ANSI_RED),
        ("[SCALE UP ACTION]", ANSI_RED),
        ("[SCALE UP CAP]", ANSI_YELLOW),
        ("[BOTTLENECK FORWARD]", ANSI_YELLOW),
        ("[COOLDOWN HOLD]", ANSI_YELLOW),
        ("[SCALE DOWN ACTION]", ANSI_CYAN),
        ("[SCALE DOWN CHECK]", ANSI_CYAN),
        ("[HOLD]", ANSI_GREEN),
    )

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)

        if not ENABLE_COLOURED_LOGS:
            return message

        # Keep large multi-line state blocks plain. Only compact action lines are
        # highlighted. The bottleneck diagnosis table still colours selected cells
        # where the table is constructed.
        raw_message = record.getMessage()

        if record.levelno >= logging.ERROR or "[ERROR]" in raw_message:
            return f"{ANSI_RED}{message}{ANSI_RESET}"

        if record.levelno == logging.WARNING:
            return f"{ANSI_YELLOW}{message}{ANSI_RESET}"

        for marker, colour in self.ACTION_COLOURS:
            if marker in raw_message:
                return f"{colour}{message}{ANSI_RESET}"

        return message


class PlainFormatter(logging.Formatter):
    """Plain formatter for file logs; strips ANSI codes from coloured table rows."""

    def format(self, record: logging.LogRecord) -> str:
        import re
        message = super().format(record)
        return re.sub(r"\x1b\[[0-9;]*m", "", message)


def configure_logging() -> None:
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    plain_formatter = PlainFormatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleColourFormatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(plain_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


configure_logging()


def valid_number(x: float) -> bool:
    return x is not None and math.isfinite(x) and x >= 0


def is_nonzero(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, dict):
        return any(is_nonzero(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return bool(value)


def erlang_c(lambda_rps: float, mu: float, c: int) -> float:
    """Return P(W>0) for an M/M/c queue."""
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


def top_tail_bottlenecks(
    deployment: str,
    node_type: str,
    downstream_tail: dict[str, float],
) -> list[tuple[str, float | str]]:
    if node_type == "leaf":
        return [(deployment, "self")]

    ranked = sorted(
        downstream_tail.items(),
        key=lambda item: item[1] or 0.0,
        reverse=True,
    )

    return ranked[:3]




def median(values: list[float]) -> float | None:
    """Return median of a non-empty numeric list."""
    clean = sorted(float(v) for v in values if valid_number(v) and v > 0)
    if not clean:
        return None
    n = len(clean)
    mid = n // 2
    if n % 2 == 1:
        return clean[mid]
    return 0.5 * (clean[mid - 1] + clean[mid])


def mean(values: list[float]) -> float | None:
    """Return arithmetic mean of a non-empty numeric list."""
    clean = [float(v) for v in values if valid_number(v) and v > 0]
    if not clean:
        return None
    return sum(clean) / len(clean)


def percentile(values: list[float], q: float) -> float | None:
    """Return linearly interpolated percentile of positive healthy samples.

    For bottleneck detection, q=0.25 means: use the 25th percentile of the
    stored healthy selected-tail values, not the live P25 latency metric.
    """
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


def healthy_stat_mode() -> str:
    """Return which healthy statistic should drive bottleneck detection/scaling.

    BOTTLENECK_HEALTHY_STAT supports:
      - "p25" (default): 25th percentile of stored healthy selected-tail/ratio samples
      - "median": robust midpoint of stored healthy samples
      - "mean": previous behaviour
    """
    mode = os.getenv("BOTTLENECK_HEALTHY_STAT", "p25").strip().lower()
    if mode not in {"mean", "median", "p25"}:
        logging.warning(
            "[CONFIG] Invalid BOTTLENECK_HEALTHY_STAT=%r; falling back to p25",
            mode,
        )
        return "p25"
    return mode


def healthy_stat(values: list[float], mode: str | None = None) -> float | None:
    """Return selected statistic of stored healthy samples."""
    selected = (mode or healthy_stat_mode()).strip().lower()
    if selected == "mean":
        return mean(values)
    if selected == "median":
        return median(values)
    return percentile(values, 0.25)


def threshold_snapshot_ms(
    threshold_history_ms: dict[str, list[float]],
    mode: str | None = None,
) -> dict[str, float]:
    """Return current allowed selected-tail per child using configured healthy statistic."""
    selected_mode = mode or healthy_stat_mode()
    snapshot: dict[str, float] = {}
    for child, values in threshold_history_ms.items():
        value = healthy_stat(values, selected_mode)
        if value is not None:
            snapshot[child] = value
    return snapshot


def healthy_selected_tail_stats_snapshot_ms(threshold_history_ms: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Return healthy selected-tail p25/mean/median/count per child for debugging and analysis."""
    snapshot: dict[str, dict[str, float]] = {}
    for child, values in threshold_history_ms.items():
        p25 = percentile(values, 0.25)
        med = median(values)
        avg = mean(values)
        count = len([v for v in values if valid_number(v) and v > 0])
        if p25 is not None and med is not None and avg is not None and count > 0:
            snapshot[child] = {
                "p25": p25,
                "mean": avg,
                "median": med,
                "count": float(count),
            }
    return snapshot

def healthy_tail_stats_snapshot_ms(threshold_history_ms: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Return healthy selected-tail p25/mean/median/count per child for debugging and analysis."""
    return healthy_selected_tail_stats_snapshot_ms(threshold_history_ms)


def tail_metric_key(label: str) -> str:
    """Return lower-case metric key such as p90 or p95 for logs/message compatibility."""
    return (label or "P95").strip().lower()


def metric_value(record: dict[str, Any], base: str, tail_label: str, default: float = float("nan")) -> Any:
    """Read a generic tail field first, then selected-tail-specific field."""
    key = tail_metric_key(tail_label)
    for candidate in (f"{base}_tail_ms", f"{base}_{key}_ms"):
        if candidate in record:
            return record[candidate]
    return default


def get_allowed_tail_ms(
    threshold_history_ms: dict[str, list[float]],
    child: str,
    fallback_ms: float | None = None,
    mode: str | None = None,
) -> float | None:
    """Allowed child selected-tail = configured healthy statistic when available.

    The parent target/source selected-tail is used only as a fallback when no healthy
    history exists. It must NOT cap the healthy statistic value, because the
    protocol defines the relief target as returning the child edge to its own
    healthy selected-tail baseline.
    """
    value = healthy_stat(threshold_history_ms.get(child, []), mode)
    if value is not None:
        return value
    if valid_number(fallback_ms) and fallback_ms and fallback_ms > 0:
        return float(fallback_ms)
    return None


def update_normal_downstream_thresholds(
    threshold_history_ms: dict[str, list[float]],
    downstream_tail_ms: dict[str, float],
    max_samples: int = 30,
) -> None:
    """Store healthy per-downstream selected-tail samples.

    The allowed selected-tail sent in bottleneck messages is the mean of this healthy
    history, not the maximum. This avoids one historical spike making the
    allowed threshold permanently too loose.
    """
    for child, tail_ms in downstream_tail_ms.items():
        if child in EXTERNAL_UPSTREAMS or child in (None, ""):
            continue
        if not valid_number(tail_ms) or tail_ms <= 0:
            continue
        values = threshold_history_ms.setdefault(child, [])
        values.append(float(tail_ms))
        if len(values) > max_samples:
            del values[: len(values) - max_samples]


def update_normal_downstream_ratio_thresholds(
    ratio_history: dict[str, list[float]],
    self_tail_ms: float,
    downstream_tail_ms: dict[str, float],
    max_samples: int = 40,
) -> None:
    """Store healthy per-downstream latency-share ratios.

    Ratio is defined as child_current_tail / this_node_current_tail. It is stored
    only in the same healthy windows used for downstream selected-tail baselines.
    """
    if not valid_number(self_tail_ms) or self_tail_ms <= 0:
        return

    for child, child_tail_ms in downstream_tail_ms.items():
        if child in EXTERNAL_UPSTREAMS or child in (None, ""):
            continue
        if not valid_number(child_tail_ms) or child_tail_ms <= 0:
            continue
        ratio = float(child_tail_ms) / float(self_tail_ms)
        if not valid_number(ratio):
            continue
        values = ratio_history.setdefault(child, [])
        values.append(ratio)
        if len(values) > max_samples:
            del values[: len(values) - max_samples]


def healthy_ratio_stats_snapshot(
    ratio_history: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """Return healthy ratio p25/mean/median/count per child for debugging and detection."""
    snapshot: dict[str, dict[str, float]] = {}
    for child, values in ratio_history.items():
        p25 = percentile(values, 0.25)
        med = median(values)
        avg = mean(values)
        count = len([v for v in values if valid_number(v) and v > 0])
        if p25 is not None and med is not None and avg is not None and count > 0:
            snapshot[child] = {
                "p25": p25,
                "mean": avg,
                "median": med,
                "count": float(count),
            }
    return snapshot


def update_healthy_self_tail_history(
    history_ms: list[float],
    self_tail_ms: float,
    local_slo_ms: float,
    max_samples: int = 40,
) -> bool:
    """Store this service's own healthy selected-tail samples.

    A sample is learned only when this service is locally healthy, i.e. the
    selected tail latency (P90 or P95 depending on SLO_LATENCY_PERCENTILE) is
    positive and does not exceed the configured local SLO. The stored P25 of
    this history is used as the local scale-down guideline.
    """
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
    """Return P25 of recent healthy P90 values for local return-to-normal scaling."""
    return percentile(history_ms, 0.25)


def update_healthy_p90_guideline(
    history_ms: list[float],
    p90_ms: float,
    local_slo_ms: float,
    received_bottleneck: bool,
    max_samples: int = 40,
) -> bool:
    """Record a normal-state P95 sample if this service is not under SLO pressure.

    This deliberately does not require P95 <= local_slo_ms. Some services have a
    normal P95 above the generic local SLO, so the learned target is defined as
    P25(recent P95 values observed when no frontend/bottleneck pressure arrives).
    """
    if received_bottleneck:
        return False
    if not valid_number(p90_ms) or p90_ms <= 0:
        return False

    history_ms.append(float(p90_ms))
    if len(history_ms) > max_samples:
        del history_ms[: len(history_ms) - max_samples]
    return True


def update_bottleneck_memory_from_messages(
    messages: list[dict[str, Any]],
    bottleneck_memory: dict[str, int],
) -> None:
    """Count bottleneck alerts by upstream parent.

    The scale-down waiting window is determined by the largest per-upstream
    counter. This keeps services that were repeatedly blamed by any upstream
    more conservative when shedding replicas.
    """
    for msg in messages:
        if msg.get("type") not in {"MSG_BOTTLENECK_ALERT", "MSG_FRONTEND_SLO_VIOLATION"}:
            continue
        data = msg.get("data") or {}
        parent = data.get("from") or msg.get("from") or "unknown"
        bottleneck_memory[parent] = int(bottleneck_memory.get(parent, 0)) + 1


def required_scale_down_windows(bottleneck_memory: dict[str, int]) -> int:
    """Return required consecutive safe windows before scale-down.

    The window is driven by the largest per-upstream bottleneck count, but is
    never less than 2. With the default 15s DAS interval, this gives a minimum
    30s proof-of-stability period before each scale-down.
    """
    min_scale_down_windows = int(os.getenv("SCALE_DOWN_MIN_WINDOWS", "2"))
    clean = [
        int(v)
        for v in bottleneck_memory.values()
        if isinstance(v, (int, float)) and v > 0
    ]
    memory_windows = max(clean) if clean else 0
    return max(min_scale_down_windows, memory_windows)


def decay_bottleneck_memory_after_downscale(bottleneck_memory: dict[str, int]) -> None:
    """Earn back one unit of trust after a successful downscale."""
    for parent in list(bottleneck_memory.keys()):
        bottleneck_memory[parent] = max(0, int(bottleneck_memory[parent]) - 1)
        if bottleneck_memory[parent] <= 0:
            del bottleneck_memory[parent]


def predict_tail_mmc_ms(
    lambda_rps: float,
    mu: float,
    replicas: int,
    service_time_s: float,
    queue_percentile: float,
) -> float:
    """Predict S + Wq_MMC at the configured percentile in milliseconds."""
    if replicas <= 0 or not valid_number(lambda_rps) or not valid_number(mu) or not valid_number(service_time_s):
        return float("nan")
    wq_s = waiting_percentile_mmc(lambda_rps, mu, replicas, queue_percentile)
    if not math.isfinite(wq_s):
        return float("inf") if wq_s == float("inf") else float("nan")
    return (service_time_s + wq_s) * 1000.0


def detect_downstream_bottlenecks(
    upstream_source_tail_ms: float,
    self_tail_ms: float,
    downstream_tail_ms: dict[str, float],
    threshold_history_ms: dict[str, list[float]],
    ratio_history: dict[str, list[float]],
    require_source_dominance: bool = True,
    parent_target_tail_ms: float | None = None,
    tail_label: str = "P95",
) -> list[dict[str, Any]]:
    bottlenecks: list[dict[str, Any]] = []
    metric_key = tail_metric_key(tail_label)
    baseline_mode = healthy_stat_mode()
    thresholds = threshold_snapshot_ms(threshold_history_ms, baseline_mode)
    healthy_stats = healthy_selected_tail_stats_snapshot_ms(threshold_history_ms)
    ratio_stats = healthy_ratio_stats_snapshot(ratio_history)

    for child, current_tail_ms in downstream_tail_ms.items():
        if child in EXTERNAL_UPSTREAMS or child in (None, ""):
            continue
        if not valid_number(current_tail_ms) or current_tail_ms <= 0:
            continue

        threshold_ms = thresholds.get(child)
        child_stats = healthy_stats.get(child, {})
        child_ratio_stats = ratio_stats.get(child, {})

        healthy_ratio_mean = child_ratio_stats.get("mean")
        healthy_ratio_median = child_ratio_stats.get("median", float("nan"))
        healthy_ratio_selected = child_ratio_stats.get(baseline_mode)
        healthy_ratio_count = child_ratio_stats.get("count", 0.0)

        current_ratio = (
            float(current_tail_ms) / float(self_tail_ms)
            if valid_number(self_tail_ms) and self_tail_ms > 0
            else float("nan")
        )

        has_healthy_info = (
            threshold_ms is not None
            and valid_number(threshold_ms)
            and threshold_ms > 0
            and healthy_ratio_selected is not None
            and valid_number(healthy_ratio_selected)
            and healthy_ratio_selected > 0
        )

        exceeds_node_source = (
            valid_number(upstream_source_tail_ms)
            and upstream_source_tail_ms > 0
            and current_tail_ms > upstream_source_tail_ms
        )

        if has_healthy_info:
            exceeds_healthy_baseline = current_tail_ms > threshold_ms
            exceeds_healthy_ratio_baseline = (
                valid_number(current_ratio)
                and current_ratio > healthy_ratio_selected
            )

            if require_source_dominance:
                is_bottleneck = (
                    exceeds_node_source
                    and exceeds_healthy_baseline
                    and exceeds_healthy_ratio_baseline
                )
                reason = f"exceeds_source_{metric_key}_healthy_{baseline_mode}_and_ratio_{baseline_mode}"
            else:
                is_bottleneck = (
                    exceeds_healthy_baseline
                    and exceeds_healthy_ratio_baseline
                )
                reason = f"single_child_exceeds_healthy_{baseline_mode}_and_ratio_{baseline_mode}"

            allowed_tail_ms = float(threshold_ms)

        else:
            is_bottleneck = require_source_dominance and exceeds_node_source
            reason = f"cold_start_multi_child_child_{metric_key}_gt_parent_{metric_key}"

            allowed_tail_ms = (
                float(parent_target_tail_ms)
                if valid_number(parent_target_tail_ms) and parent_target_tail_ms and parent_target_tail_ms > 0
                else float(upstream_source_tail_ms)
                if valid_number(upstream_source_tail_ms) and upstream_source_tail_ms > 0
                else float(current_tail_ms)
            )

        if not is_bottleneck:
            continue

        bottlenecks.append({
            "service": child,
            "tail_label": tail_label,
            "current_tail_ms": float(current_tail_ms),
            "upstream_source_tail_ms": float(upstream_source_tail_ms) if valid_number(upstream_source_tail_ms) else float("nan"),
            "self_tail_ms": float(self_tail_ms) if valid_number(self_tail_ms) else float("nan"),
            f"current_{metric_key}_ms": float(current_tail_ms),
            f"upstream_source_{metric_key}_ms": float(upstream_source_tail_ms) if valid_number(upstream_source_tail_ms) else float("nan"),
            f"self_{metric_key}_ms": float(self_tail_ms) if valid_number(self_tail_ms) else float("nan"),
            "current_ratio": float(current_ratio) if valid_number(current_ratio) else float("nan"),
            "healthy_ratio_mean": float(healthy_ratio_mean) if valid_number(healthy_ratio_mean) else float("nan"),
            "healthy_ratio_median": float(healthy_ratio_median) if valid_number(healthy_ratio_median) else float("nan"),
            "healthy_ratio_selected": float(healthy_ratio_selected) if valid_number(healthy_ratio_selected) else float("nan"),
            "healthy_stat_mode": baseline_mode,
            "healthy_ratio_sample_count": int(healthy_ratio_count),
            "threshold_tail_ms": float(threshold_ms) if valid_number(threshold_ms) else float("nan"),
            "healthy_selected_tail_ms": float(threshold_ms) if valid_number(threshold_ms) else float("nan"),
            "healthy_p25_tail_ms": float(child_stats.get("p25", float("nan"))) if valid_number(child_stats.get("p25", float("nan"))) else float("nan"),
            "healthy_mean_tail_ms": float(child_stats.get("mean", float("nan"))) if valid_number(child_stats.get("mean", float("nan"))) else float("nan"),
            "healthy_median_tail_ms": float(child_stats.get("median", float("nan"))) if valid_number(child_stats.get("median", float("nan"))) else float("nan"),
            f"threshold_{metric_key}_ms": float(threshold_ms) if valid_number(threshold_ms) else float("nan"),
            f"healthy_selected_{metric_key}_ms": float(threshold_ms) if valid_number(threshold_ms) else float("nan"),
            f"healthy_p25_{metric_key}_ms": float(child_stats.get("p25", float("nan"))) if valid_number(child_stats.get("p25", float("nan"))) else float("nan"),
            f"healthy_mean_{metric_key}_ms": float(child_stats.get("mean", float("nan"))) if valid_number(child_stats.get("mean", float("nan"))) else float("nan"),
            f"healthy_median_{metric_key}_ms": float(child_stats.get("median", float("nan"))) if valid_number(child_stats.get("median", float("nan"))) else float("nan"),
            "healthy_sample_count": int(child_stats.get("count", 0)),
            "allowed_tail_ms": float(allowed_tail_ms),
            f"allowed_{metric_key}_ms": float(allowed_tail_ms),
            "reason": reason,
        })

    return bottlenecks
    
    
def choose_bottleneck_target_ms(messages: list[dict[str, Any]]) -> tuple[bool, float | None, str | None]:
    """Return whether this service received frontend/root scaling pressure.

    Accepted message types:
      - MSG_BOTTLENECK_ALERT: targeted bottleneck alert
      - MSG_FRONTEND_SLO_VIOLATION: root/frontend broadcast to all downstreams

    If multiple parents send messages, use the strictest explicit target when present.
    A frontend SLO broadcast may not carry an allowed_tail_ms; in that case this
    returns received=True and allowed=None, so the service can use its own
    learned healthy-P95 target.
    """
    received_pressure = False
    targets: list[tuple[float, str | None]] = []

    for msg in messages:
        msg_type = msg.get("type")
        if msg_type not in {"MSG_BOTTLENECK_ALERT", "MSG_FRONTEND_SLO_VIOLATION"}:
            continue

        received_pressure = True
        data = msg.get("data") or {}
        allowed = data.get("allowed_tail_ms")
        if valid_number(allowed) and allowed > 0:
            targets.append((float(allowed), data.get("from") or msg.get("from")))

    if targets:
        allowed_ms, parent = min(targets, key=lambda x: x[0])
        return True, allowed_ms, parent

    if received_pressure:
        parent = None
        for msg in messages:
            if msg.get("type") in {"MSG_BOTTLENECK_ALERT", "MSG_FRONTEND_SLO_VIOLATION"}:
                data = msg.get("data") or {}
                parent = data.get("from") or msg.get("from")
                break
        return True, None, parent

    return False, None, None


def recommend_replicas_for_target_tail_mmc(
    lambda_rps: float,
    mu: float,
    target_tail_ms: float,
    service_time_s: float,
    min_replicas: int,
    max_replicas: int,
    current_replicas: int,
    queue_percentile: float,
) -> int:
    """Use M/M/c to find replicas satisfying S + Wq_tail <= target_tail.

    The tail percentile is supplied by QUEUE_MODEL_PERCENTILE:
      - p90 -> queue_percentile=0.90
      - p95 -> queue_percentile=0.95
    """
    if not valid_number(target_tail_ms) or target_tail_ms <= 0:
        return current_replicas

    wq_allowed_s = (target_tail_ms / 1000.0) - service_time_s
    if wq_allowed_s < 0:
        return max_replicas

    return recommend_replicas_slo_mmc(
        lambda_rps=lambda_rps,
        mu=mu,
        wq_allowed_s=max(0.001, wq_allowed_s),
        min_replicas=min_replicas,
        max_replicas=max_replicas,
        current_replicas=current_replicas,
        queue_percentile=queue_percentile,
    )

def send_bottleneck_alert(
    p2p_agent: P2PAgent,
    target: str,
    parent: str,
    allowed_tail_ms: float,
    current_tail_ms: float,
    reason: str,
    tail_label: str = "P95",
) -> bool:
    payload = {
        "from": parent,
        "you_are_bottleneck": True,
        "tail_label": tail_label,
        "allowed_tail_ms": float(allowed_tail_ms),
        "observed_tail_ms": float(current_tail_ms),
        "reason": reason,
        "timestamp": time.time(),
    }
    return p2p_agent.send_message(target, "MSG_BOTTLENECK_ALERT", payload)


def send_frontend_slo_violation_broadcast(
    p2p_agent: P2PAgent,
    target: str,
    parent: str,
    frontend_tail_ms: float,
    frontend_slo_ms: float,
    tail_label: str = "P95",
) -> bool:
    """Broadcast frontend/root SLO violation to every downstream service.

    This is not saying every downstream is a bottleneck. It tells each service
    to compare current load against its own healthy-P95 guideline and use M/M/c
    to return to that local normal state if needed.
    """
    payload = {
        "from": parent,
        "frontend_slo_violated": True,
        "tail_label": tail_label,
        "frontend_tail_ms": float(frontend_tail_ms),
        "frontend_slo_ms": float(frontend_slo_ms),
        "reason": "frontend_slo_violation_broadcast",
        "timestamp": time.time(),
    }
    return p2p_agent.send_message(target, "MSG_FRONTEND_SLO_VIOLATION", payload)

def merge_dict_metric(
    http_dict: dict[str, float] | None,
    grpc_dict: dict[str, float] | None,
) -> dict[str, float]:
    merged: dict[str, float] = {}

    for d in (http_dict or {}, grpc_dict or {}):
        for key, value in d.items():
            if key in EXTERNAL_UPSTREAMS:
                continue
            merged[key] = merged.get(key, 0.0) + (value or 0.0)

    return {k: v for k, v in merged.items() if is_nonzero(v)}


def expected_queueing_delay(lambda_rps: float, mu: float, c: int) -> float:
    """Return expected queueing delay Wq in seconds."""
    if not valid_number(lambda_rps) or not valid_number(mu):
        return float("nan")

    if c <= 0 or mu <= 0:
        return float("nan")

    capacity = c * mu

    if capacity <= lambda_rps:
        return float("inf")

    p_wait = erlang_c(lambda_rps, mu, c)

    if not valid_number(p_wait):
        return float("nan")

    return p_wait / (capacity - lambda_rps)


def classify_node(
    deployment: str,
    upstreams: list[str],
    downstreams: list[str],
) -> str:
    if deployment in ROOT_SERVICES:
        return "root"
    if downstreams:
        return "intermediate"
    return "leaf"


def recommend_replicas_slo_mmc(
    lambda_rps: float,
    mu: float,
    wq_allowed_s: float,
    min_replicas: int,
    max_replicas: int,
    current_replicas: int,
    queue_percentile: float = 0.95,
) -> int:
    """Find minimum c such that modeled Wq satisfies SLO."""
    if not all(valid_number(x) for x in [lambda_rps, mu, wq_allowed_s]):
        print(f"Invalid input for recommend_replicas_slo_mmc: lambda_rps={lambda_rps}, mu={mu}, wq_allowed_s={wq_allowed_s}", flush=True)
        return current_replicas

    if lambda_rps <= 0 or mu <= 0 or wq_allowed_s < 0:
        print(f"Non-positive input for recommend_replicas_slo_mmc: lambda_rps={lambda_rps}, mu={mu}, wq_allowed_s={wq_allowed_s}", flush=True)
        return current_replicas

    for c in range(min_replicas, max_replicas + 1):
        wq_model_s = waiting_percentile_mmc(lambda_rps, mu, c, queue_percentile)
        #wq_model_s = expected_queueing_delay(lambda_rps, mu, c)

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
    """Find minimum c such that calibrated G/G/c-like selected-tail queueing delay satisfies SLO.

    Uses M/M/c selected-tail queue delay as the base and multiplies it by
    k_variability to account for burstiness/service-time variability:

        Wq_tail_GGc ≈ k_variability * Wq_tail_MMc
    """
    if not all(valid_number(x) for x in [lambda_rps, mu, k_variability, wq_allowed_s]):
        print(
            f"Invalid input for recommend_replicas_slo_ggc: "
            f"lambda_rps={lambda_rps}, mu={mu}, k={k_variability}, "
            f"wq_allowed_s={wq_allowed_s}",
            flush=True,
        )
        return current_replicas

    if lambda_rps <= 0 or mu <= 0 or k_variability <= 0 or wq_allowed_s < 0:
        print(
            f"Non-positive input for recommend_replicas_slo_ggc: "
            f"lambda_rps={lambda_rps}, mu={mu}, k={k_variability}, "
            f"wq_allowed_s={wq_allowed_s}",
            flush=True,
        )
        return current_replicas

    for c in range(min_replicas, max_replicas + 1):
        wq_tail_mmc_s = waiting_percentile_mmc(lambda_rps, mu, c, queue_percentile)
        wq_tail_ggc_s = k_variability * wq_tail_mmc_s

        if math.isfinite(wq_tail_ggc_s) and wq_tail_ggc_s <= wq_allowed_s:
            return c

    return max_replicas



def expected_queueing_delay_mmc(lambda_rps, mu, c):
    if c <= 0 or mu <= 0 or lambda_rps < 0:
        return float("nan")
    if lambda_rps >= c * mu:
        return float("inf")

    pw = erlang_c(lambda_rps, mu, c)
    return pw / (c * mu - lambda_rps)

def waiting_percentile_mmc(lambda_rps, mu, c, percentile):
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
    
def calculate_processing_time_mmc(
    r_avg_s: float,
    r_p50_s: float,
    r_p90_s: float,
    r_p95_s: float,
    c: int,
    lambda_rps: float,
) -> float:
    best_s = max(0.001, r_p50_s)
    best_error = float("inf")

    # Search possible S from 0.1 ms to just below observed P95
    for i in range(1, 3000):
        s = i / 10000.0  # 0.1 ms to 299.9 ms
        mu = 1.0 / s

        if lambda_rps >= c * mu:
            continue

        wq_avg = expected_queueing_delay_mmc(lambda_rps, mu, c)
        wq50 = waiting_percentile_mmc(lambda_rps, mu, c, 0.50)
        wq90 = waiting_percentile_mmc(lambda_rps, mu, c, 0.90)
        wq95 = waiting_percentile_mmc(lambda_rps, mu, c, 0.95)

        pred_avg = s + wq_avg
        pred_p50 = s + wq50
        pred_p90 = s + wq90
        pred_p95 = s + wq95

        error = (
            1.0 * (pred_avg - r_avg_s) ** 2
            + 0.5 * (pred_p50 - r_p50_s) ** 2
            + 1.0 * (pred_p90 - r_p90_s) ** 2
            + 2.0 * (pred_p95 - r_p95_s) ** 2
        )

        if error < best_error:
            best_error = error
            best_s = s

    return best_s, best_error
    
def build_bottleneck_diagnosis_table(
    deployment: str,
    node_type: str,
    frontend_slo_violated: bool,
    received_bottleneck: bool,
    received_allowed_tail_ms: float | None,
    bottleneck_parent: str | None,
    upstream_source_tail_ms: float,
    self_tail_ms: float,
    downstream_tail_ms: dict[str, float],
    threshold_history_ms: dict[str, list[float]],
    ratio_history: dict[str, list[float]],
    bottleneck_candidates: list[dict[str, Any]],
    tail_label: str = "P95",
) -> str:
    stats = healthy_tail_stats_snapshot_ms(threshold_history_ms)
    ratio_stats = healthy_ratio_stats_snapshot(ratio_history)
    bottleneck_by_service = {b["service"]: b for b in bottleneck_candidates}
    metric_label = tail_label.upper()
    metric_key = tail_metric_key(tail_label)

    lines = []
    lines.append("\n[[BOTTLENECK-AWARE REACTIVE DIAGNOSIS]]")
    lines.append(
        f"State: service={deployment} | node_type={node_type} | "
        f"frontend_slo_violated={frontend_slo_violated} | "
        f"received_bottleneck={received_bottleneck} | "
        f"allowed_{metric_key}={received_allowed_tail_ms:.2f}ms" if received_allowed_tail_ms is not None else
        f"State: service={deployment} | node_type={node_type} | "
        f"frontend_slo_violated={frontend_slo_violated} | "
        f"received_bottleneck={received_bottleneck} | "
        f"allowed_{metric_key}=None"
    )
    lines.append(f"Parent: {bottleneck_parent or 'None'} | Upstream source {metric_label}: {upstream_source_tail_ms:.2f} ms")
    lines.append("")
    lines.append("[Downstream Bottleneck Diagnosis Table]")
    lines.append(
        "    "
        f"{'Downstream':<24} | "
        f"{('Current ' + metric_label):>11} | "
        f"{('Src ' + metric_label):>8} | "
        f"{'Healthy P25':>11} | "
        f"{'Healthy Mean':>12} | "
        f"{'Healthy Median':>14} | "
        f"{'N':>3} | "
        f"{'Cur Ratio':>9} | "
        f"{'Ratio P25':>9} | "
        f"{'Ratio Mean':>10} | "
        f"{'Ratio Median':>12} | "
        f"{'RN':>3} | "
        f"{'Allowed':>9} | "
        f"{'Bottleneck':>10} | "
        f"{'Reason':<44}"
    )
    lines.append("    " + "-" * 190)

    for child in sorted(downstream_tail_ms.keys()):
        if child in EXTERNAL_UPSTREAMS or child in (None, ""):
            continue

        current = downstream_tail_ms.get(child, float("nan"))
        child_stats = stats.get(child, {})
        p25 = child_stats.get("p25", float("nan"))
        mean = child_stats.get("mean", float("nan"))
        med = child_stats.get("median", float("nan"))
        n = int(child_stats.get("count", 0))

        child_ratio_stats = ratio_stats.get(child, {})
        ratio_p25 = child_ratio_stats.get("p25", float("nan"))
        ratio_mean = child_ratio_stats.get("mean", float("nan"))
        ratio_med = child_ratio_stats.get("median", float("nan"))
        ratio_n = int(child_ratio_stats.get("count", 0))

        current_ratio = (
            current / self_tail_ms
            if valid_number(current) and valid_number(self_tail_ms) and self_tail_ms > 0
            else float("nan")
        )

        b = bottleneck_by_service.get(child)
        is_bottleneck = b is not None
        baseline_mode = healthy_stat_mode()
        selected_baseline = child_stats.get(baseline_mode, float("nan"))
        allowed = metric_value(b, "allowed", metric_label) if b else selected_baseline
        reason = b.get("reason", "-") if b else "-"

        latency_ok = (
            valid_number(current)
            and valid_number(p25)
            and p25 > 0
            and current <= p25
        )

        ratio_ok = (
            valid_number(current_ratio)
            and valid_number(ratio_p25)
            and ratio_p25 > 0
            and current_ratio <= ratio_p25
        )

        bottleneck_ok = not is_bottleneck

        latency_colour = ANSI_GREEN if latency_ok else ANSI_RED
        ratio_colour = ANSI_GREEN if ratio_ok else ANSI_RED
        bottleneck_colour = ANSI_GREEN if bottleneck_ok else ANSI_RED

        ok_count = sum([latency_ok, ratio_ok, bottleneck_ok])

        if ok_count == 3:
            downstream_colour = ANSI_GREEN
        elif ok_count == 0:
            downstream_colour = ANSI_RED
        else:
            downstream_colour = ANSI_YELLOW

        downstream_cell = colour_text(f"-> {child:<22}", downstream_colour)
        current_tail_cell = colour_text(f"{current:>8.2f} ms", latency_colour)
        current_ratio_cell = colour_text(f"{current_ratio:>9.3f}", ratio_colour)
        bottleneck_cell = colour_text(
            f"{'YES' if is_bottleneck else 'no':>10}",
            bottleneck_colour,
        )

        row = (
            "    "
            f"{downstream_cell} | "
            f"{current_tail_cell} | "
            f"{upstream_source_tail_ms:>5.2f} ms | "
            f"{p25:>8.2f} ms | "
            f"{mean:>9.2f} ms | "
            f"{med:>11.2f} ms | "
            f"{n:>3} | "
            f"{current_ratio_cell} | "
            f"{ratio_p25:>9.3f} | "
            f"{ratio_mean:>10.3f} | "
            f"{ratio_med:>12.3f} | "
            f"{ratio_n:>3} | "
            f"{allowed:>6.2f} ms | "
            f"{bottleneck_cell} | "
            f"{reason:<44}"
        )

        lines.append(row)

    return "\n".join(lines) + "\n"





# NOTE: The newer isolated/local service-time estimator has been removed on purpose.
# We do not know whether downstream latency decomposition is correct for this system,
# because downstream calls may be serial, parallel, async, cached, retried, or partially
# overlapped. Therefore, the queueing model uses a fixed processing time learned from
# low-load observations, where queueing delay should be minimal.


def das_loop(
    monitor: Monitor,
    executor: Executor,
    p2p_agent: P2PAgent,
    deployment: str,
    interval: float,
    scale_up_cooldown: float,
    scale_down_cooldown: float,
    min_replicas: int,
    max_replicas: int,
) -> None:
    # Independent directional cooldown trackers
    last_scale_up_time = 0.0
    last_scale_down_time = 0.0
    last_processing_time_update = 0.0
    learned_processing_time_s = None
    # Per-downstream healthy selected-tail and latency-share ratio histories observed when this service is healthy.
    normal_downstream_tail_history_ms: dict[str, list[float]] = {}
    normal_downstream_ratio_history: dict[str, list[float]] = {}
    # This service's own healthy P90 history. Its P25 is used as the return-to-normal target after bottleneck alerts.
    healthy_self_p90_history_ms: list[float] = []
    # Per-upstream bottleneck memory. Required scale-down windows = max value.
    recent_bottleneck_count_by_parent: dict[str, int] = {}
    scale_down_ok_windows = 0
    # Messages caught during the sleep/poll phase so they are not lost.
    pending_messages: list[dict[str, Any]] = []
    message_poll_interval = float(os.getenv("MESSAGE_POLL_INTERVAL_SECONDS", "1"))
    last_variability_update = 0.0
    learned_variability_k = float(os.getenv("GGC_INITIAL_K", "1.0"))

    service_time_update_interval = float(os.getenv("SERVICE_TIME_UPDATE_INTERVAL_SECONDS", "29"))
    service_time_alpha = float(os.getenv("SERVICE_TIME_EWMA_ALPHA", "0.8"))
    # Service-time EWMA learning now updates from P25 at every update interval.
    # rho is still computed/logged for diagnosis, but it no longer gates S updates.
    service_time_update_rho_max = float(os.getenv("SERVICE_TIME_UPDATE_RHO_MAX", "0.5"))
    bottleneck_healthy_stat = healthy_stat_mode()
    healthy_threshold_max_samples = int(os.getenv("BOTTLENECK_HEALTHY_THRESHOLD_SAMPLES", "40"))
    # Healthy latency/ratio baselines are empirical acceptable envelopes.
    # They are recorded whenever the local/root SLO condition is healthy,
    # independent of rho. Rho is used only for service-time learning.
    single_child_forward_fraction = float(os.getenv("BOTTLENECK_SINGLE_CHILD_FORWARD_FRACTION", "0.5"))
    max_scale_up_step = int(os.getenv("MAX_SCALE_UP_STEP", "2"))
    scale_down_step = int(os.getenv("SCALE_DOWN_STEP", "1"))

    variability_update_interval = float(os.getenv("GGC_K_UPDATE_INTERVAL_SECONDS", "180"))
    variability_alpha = float(os.getenv("GGC_K_EWMA_ALPHA", "0.8"))
    variability_k_min = float(os.getenv("GGC_K_MIN", "0.5"))
    variability_k_max = float(os.getenv("GGC_K_MAX", "10.0"))
    # Fixed baseline processing time.
    # Prefer the calibrated per-service baseline table, with optional
    # deployment-specific and global environment overrides.
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
        "Starting DAS for deployment '%s' [Interval: %.1fs | Up Cooldown: %.1fs, Down Cooldown: %.1fs | HealthyStat: %s]",
        deployment, interval, scale_up_cooldown, scale_down_cooldown, bottleneck_healthy_stat
    )
    
    # Full monitoring / frontend detection interval. Default: 15s.
    interval = float(os.getenv("NORMAL_DETECTION_INTERVAL_SECONDS", "15"))

    def wait_for_next_loop(timeout_s: float) -> None:
        """Sleep in short polls so bottleneck messages wake the DAS loop early.

        P2PAgent remains message-only: we do not require an event/callback.
        We poll its inbox every MESSAGE_POLL_INTERVAL_SECONDS. Any messages
        found are stored in pending_messages and processed at the top of the
        next loop iteration, so they are not lost.
        """
        nonlocal pending_messages
        deadline = time.time() + max(0.0, timeout_s)
        while time.time() < deadline:
            new_messages = p2p_agent.get_messages()
            if new_messages:
                pending_messages.extend(new_messages)
                logging.info(
                    "[FAST WAKE] received %d P2P message(s); waking DAS loop early",
                    len(new_messages),
                )
                return
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            time.sleep(min(message_poll_interval, remaining))
    send_hello = True
    while True:
        try:
            now = time.time()

            #############
            # Step 0: Initial Running Verification
            #############
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

            #############
            # Step 1: Monitoring
            #############
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
            http_latency_p50_as_dst = monitor.get_http_latency_p50_as_dst(deployment)
            grpc_latency_p50_as_dst = monitor.get_grpc_latency_p50_as_dst(deployment)
            http_latency_p25_as_dst = monitor.get_http_latency_p25_as_dst(deployment)
            grpc_latency_p25_as_dst = monitor.get_grpc_latency_p25_as_dst(deployment)
            http_latency_p90_as_dst = monitor.get_http_latency_p90_as_dst(deployment)
            grpc_latency_p90_as_dst = monitor.get_grpc_latency_p90_as_dst(deployment)
            http_latency_p95_as_dst = monitor.get_http_latency_p95_as_dst(deployment)
            grpc_latency_p95_as_dst = monitor.get_grpc_latency_p95_as_dst(deployment)

            http_rpm_as_src = monitor.get_http_rpm_as_src(deployment)
            grpc_rpm_as_src = monitor.get_grpc_rpm_as_src(deployment)

            http_latency_avg_as_src = monitor.get_http_latency_as_src(deployment)
            grpc_latency_avg_as_src = monitor.get_grpc_latency_as_src(deployment)
            http_latency_p50_as_src = monitor.get_http_latency_p50_as_src(deployment)
            grpc_latency_p50_as_src = monitor.get_grpc_latency_p50_as_src(deployment)
            http_latency_p25_as_src = monitor.get_http_latency_p25_as_src(deployment)
            grpc_latency_p25_as_src = monitor.get_grpc_latency_p25_as_src(deployment)
            http_latency_p90_as_src = monitor.get_http_latency_p90_as_src(deployment)
            grpc_latency_p90_as_src = monitor.get_grpc_latency_p90_as_src(deployment)
            http_latency_p95_as_src = monitor.get_http_latency_p95_as_src(deployment)
            grpc_latency_p95_as_src = monitor.get_grpc_latency_p95_as_src(deployment)

            http_rpm_mesh_as_dst = monitor.get_http_rpm_mesh_as_dst(deployment)
            grpc_rpm_mesh_as_dst = monitor.get_grpc_rpm_mesh_as_dst(deployment)

            http_latency_mesh_avg_as_dst = monitor.get_http_latency_mesh_as_dst(deployment)
            grpc_latency_mesh_avg_as_dst = monitor.get_grpc_latency_mesh_as_dst(deployment)

            http_latency_p25_mesh_as_dst = monitor.get_http_latency_p25_mesh_as_dst(deployment)
            grpc_latency_p25_mesh_as_dst = monitor.get_grpc_latency_p25_mesh_as_dst(deployment)
            http_latency_p90_mesh_as_dst = monitor.get_http_latency_p90_mesh_as_dst(deployment)
            grpc_latency_p90_mesh_as_dst = monitor.get_grpc_latency_p90_mesh_as_dst(deployment)
            http_latency_p95_mesh_as_dst = monitor.get_http_latency_p95_mesh_as_dst(deployment)
            grpc_latency_p95_mesh_as_dst = monitor.get_grpc_latency_p95_mesh_as_dst(deployment)

            http_rpm_mesh_as_src = monitor.get_http_rpm_mesh_as_src(deployment)
            grpc_rpm_mesh_as_src = monitor.get_grpc_rpm_mesh_as_src(deployment)

            http_latency_mesh_avg_as_src = monitor.get_http_latency_mesh_as_src(deployment)
            grpc_latency_mesh_avg_as_src = monitor.get_grpc_latency_mesh_as_src(deployment)

            http_latency_p25_mesh_as_src = monitor.get_http_latency_p25_mesh_as_src(deployment)
            grpc_latency_p25_mesh_as_src = monitor.get_grpc_latency_p25_mesh_as_src(deployment)
            http_latency_p90_mesh_as_src = monitor.get_http_latency_p90_mesh_as_src(deployment)
            grpc_latency_p90_mesh_as_src = monitor.get_grpc_latency_p90_mesh_as_src(deployment)
            http_latency_p95_mesh_as_src = monitor.get_http_latency_p95_mesh_as_src(deployment)
            grpc_latency_p95_mesh_as_src = monitor.get_grpc_latency_p95_mesh_as_src(deployment)

            upstreams = monitor.get_upstreams(deployment)
            downstreams = monitor.get_downstreams(deployment)

            node_type = classify_node(deployment, upstreams, downstreams)

            logging.info("Deployment '%s' node type is: %s", deployment, node_type)

            if not p2p_agent.ready:
                logging.info("P2P not ready yet for %s; skip sending messages", deployment)
            elif send_hello:
                send_hello = False
                for downstream in downstreams:
                    if downstream in ("", None, "unknown") or downstream == p2p_agent.peer_id:
                        continue

                    p2p_agent.send_message(
                        downstream,
                        "MSG_HELLO",
                        {
                            "from": p2p_agent.peer_id,
                            "msg": "hello downstream",
                            "timestamp": time.time(),
                        },
                    )

            required_metrics = {
                "http_rpm_as_dst": http_rpm_as_dst,
                "http_latency_p50_as_dst": http_latency_p50_as_dst,
                "http_latency_p25_as_dst": http_latency_p25_as_dst,
                "http_latency_p95_as_dst": http_latency_p95_as_dst,
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

            #############
            # Step 2: Queueing Model & Fixed Low-Load Processing Time
            #############
            lambda_rps = (http_rpm_as_dst + grpc_rpm_as_dst) / 60.0

            R_avg_ms = http_latency_avg_as_dst + grpc_latency_avg_as_dst
            R_p50_ms = http_latency_p50_as_dst + grpc_latency_p50_as_dst
            R_p25_ms = http_latency_p25_as_dst + grpc_latency_p25_as_dst
            R_p90_ms = http_latency_p95_as_dst + grpc_latency_p95_as_dst
            R_p90_ms = http_latency_p90_as_dst + grpc_latency_p90_as_dst
            R_source_p90_ms = http_latency_p95_as_src + grpc_latency_p95_as_src
            R_source_p90_ms = http_latency_p90_as_src + grpc_latency_p90_as_src

            slo_tail_label, slo_tail_quantile = normalize_latency_percentile(
                os.getenv("SLO_LATENCY_PERCENTILE"),
                "p95",
            )
            # Local service scaling uses P90. P95 is kept for frontend/root SLO violation detection only.
            queue_tail_label, queue_tail_quantile = ("P90", 0.90)
            R_slo_ms = R_p90_ms if slo_tail_label == "P90" else R_p90_ms
            R_source_slo_ms = R_source_p90_ms if slo_tail_label == "P90" else R_source_p90_ms

            R_avg_s = R_avg_ms / 1000.0
            R_p50_s = R_p50_ms / 1000.0
            R_p25_s = R_p25_ms / 1000.0
            R_p90_s = R_p90_ms / 1000.0
            R_p95_s = R_p90_ms / 1000.0
            R_slo_s = R_slo_ms / 1000.0

            # Processing-time assumption.
            #
            # Use a P25-like processing-time proxy. The configured baseline is
            # converted from low-load P50 using 2/3, and runtime updates use
            # live P25 latency at every update interval.
            min_processing_time_s = float(os.getenv("MIN_PROCESSING_TIME_MS", "1")) / 1000.0

            # Dynamic effective service-time estimate.
            # If fixed_processing_time_s is provided, use it only as the initial baseline.
            # After that, keep refining S during safe low-load windows.

            if learned_processing_time_s is None:
                if fixed_processing_time_s is None:
                    learned_processing_time_s = max(min_processing_time_s, R_p25_s)
                    service_time_source = "startup_p25"
                else:
                    learned_processing_time_s = max(min_processing_time_s, fixed_processing_time_s)
                    service_time_source = configured_service_time_source

                last_processing_time_update = now

                logging.info(
                    "[SERVICE TIME INIT] service=%s S=%.2fms p25=%.2fms p50=%.2fms min=%.2fms source=%s",
                    deployment,
                    learned_processing_time_s * 1000,
                    R_p25_s * 1000,
                    R_p50_s * 1000,
                    min_processing_time_s * 1000,
                    service_time_source,
                )

            else:
                elapsed_since_s_update = now - last_processing_time_update

                cached_mu_for_s_update = (
                    1.0 / learned_processing_time_s
                    if learned_processing_time_s is not None and learned_processing_time_s > 0
                    else 0.0
                )

                cached_rho_for_s_update = (
                    lambda_rps / (pods_count * cached_mu_for_s_update)
                    if cached_mu_for_s_update > 0 and pods_count > 0
                    else float("inf")
                )

                can_update_service_time = (
                    elapsed_since_s_update >= service_time_update_interval
                    and valid_number(R_p25_s)
                    and R_p25_s > min_processing_time_s
                )

                if can_update_service_time:
                    old_s = learned_processing_time_s
                    learned_processing_time_s = (
                        service_time_alpha * learned_processing_time_s
                        + (1.0 - service_time_alpha) * R_p25_s
                    )
                    last_processing_time_update = now

                    if fixed_processing_time_s is None:
                        service_time_source = "smoothed_p25_all_load"
                    else:
                        service_time_source = "smoothed_p25_all_load_from_configured_baseline"

                    logging.info(
                        "[SERVICE TIME UPDATE] service=%s old_S=%.2fms new_S=%.2fms "
                        "p25=%.2fms p50=%.2fms rho=%.3f alpha=%.2f source=%s",
                        deployment,
                        old_s * 1000,
                        learned_processing_time_s * 1000,
                        R_p25_s * 1000,
                        R_p50_s * 1000,
                        cached_rho_for_s_update,
                        service_time_alpha,
                        service_time_source,
                    )

                else:
                    service_time_source = (
                        "cached_p25"
                        if fixed_processing_time_s is None
                        else "cached_configured_baseline"
                    )

                    logging.info(
                        "[SERVICE TIME HOLD] service=%s S=%.2fms p25=%.2fms p50=%.2fms "
                        "elapsed=%.1fs interval=%.1fs rho=%.3f "
                        "valid_p25=%s p25_gt_min=%s source=%s",
                        deployment,
                        learned_processing_time_s * 1000,
                        R_p25_s * 1000,
                        R_p50_s * 1000,
                        elapsed_since_s_update,
                        service_time_update_interval,
                        cached_rho_for_s_update,
                        valid_number(R_p25_s),
                        R_p25_s > min_processing_time_s,
                        service_time_source,
                    )

            S_s = learned_processing_time_s

            mu = 1.0 / S_s if S_s > 0 else 0.0
            Wq_s = max(0.0, R_slo_s - R_p25_s)
            Q = lambda_rps * Wq_s
            rho = (lambda_rps / (pods_count * mu) if mu > 0 and pods_count > 0 else 0.0)


            # Calibrate G/G/c-like variability factor k using observed selected-tail inflation.
            # Keep S physically interpretable (smoothed P50 or fixed baseline), and let k
            # absorb burstiness/service-time variability/fanout effects:
            #   Wq95_GGc ≈ k * Wq95_MMc
            observed_tail_excess_s = max(0.0, R_slo_s - S_s)
            wq_tail_mmc_current_for_k_s = waiting_percentile_mmc(lambda_rps, mu, pods_count, queue_tail_quantile)

            if (
                now - last_variability_update >= variability_update_interval
                and math.isfinite(wq_tail_mmc_current_for_k_s)
                and wq_tail_mmc_current_for_k_s > 1e-9
                and math.isfinite(observed_tail_excess_s)
            ):
                raw_k = observed_tail_excess_s / wq_tail_mmc_current_for_k_s
                clipped_k = max(variability_k_min, min(variability_k_max, raw_k))
                old_k = learned_variability_k
                learned_variability_k = (
                    variability_alpha * learned_variability_k
                    + (1.0 - variability_alpha) * clipped_k
                )
                last_variability_update = now

                logging.info(
                    "[GGC K UPDATE] service=%s old_k=%.3f raw_k=%.3f clipped_k=%.3f new_k=%.3f observed_wq_%s=%.2fms mmc_wq_%s=%.2fms alpha=%.2f",
                    deployment,
                    old_k,
                    raw_k,
                    clipped_k,
                    learned_variability_k,
                    queue_tail_label.lower(),
                    observed_tail_excess_s * 1000,
                    queue_tail_label.lower(),
                    wq_tail_mmc_current_for_k_s * 1000,
                    variability_alpha,
                )

            k_variability = learned_variability_k

            #############
            # Step 3: Analysis & Replicas Recommendation
            #############
            rho_target = float(os.getenv("RHO_TARGET", "0.8"))

            recommended_replicas = (math.ceil(lambda_rps / (mu * rho_target)) if mu > 0 else pods_count)
            recommended_replicas = max(min_replicas, min(max_replicas, recommended_replicas))

            hpa_recommended = math.ceil(pods_count * ((cpu_utilisation / 100.0) / 0.8))
            hpa_recommended = max(min_replicas, min(max_replicas, hpa_recommended))

            # Drain P2P messages before replica recommendation so the displayed
            # effective target and SLO queue budget reflect any received upstream
            # bottleneck target in this same loop.
            incoming_messages = pending_messages + p2p_agent.get_messages()
            pending_messages = []
            update_bottleneck_memory_from_messages(incoming_messages, recent_bottleneck_count_by_parent)
            received_bottleneck, received_allowed_tail_ms, bottleneck_parent = choose_bottleneck_target_ms(incoming_messages)

            latency_slo_ms = get_configured_latency_slo_ms(node_type)

            # Learn this service's normal P95 only from healthy windows where it has
            # not received a bottleneck alert. The guideline is P25(recent healthy P90).
            healthy_p90_learned = update_healthy_p90_guideline(
                history_ms=healthy_self_p90_history_ms,
                p90_ms=R_p90_ms,
                local_slo_ms=latency_slo_ms,
                received_bottleneck=received_bottleneck,
                max_samples=healthy_threshold_max_samples,
            )
            own_healthy_p90_target_ms = healthy_p90_target_ms(healthy_self_p90_history_ms)

            if healthy_p90_learned:
                logging.info(
                    "[HEALTHY P90 LEARN] service=%s p90=%.2fms target_p25_recent_healthy_p90=%.2fms samples=%d",
                    deployment,
                    R_p90_ms,
                    own_healthy_p90_target_ms if own_healthy_p90_target_ms is not None else float("nan"),
                    len(healthy_self_p90_history_ms),
                )

            effective_latency_target_ms = latency_slo_ms
            effective_latency_target_source = "local_slo"

            if received_bottleneck:
                if own_healthy_p90_target_ms is not None:
                    effective_latency_target_ms = own_healthy_p90_target_ms
                    effective_latency_target_source = (
                        f"own_healthy_p90_p25_return_target;"
                        f"upstream:{bottleneck_parent or 'unknown'}"
                    )
                elif received_allowed_tail_ms is not None:
                    effective_latency_target_ms = received_allowed_tail_ms
                    effective_latency_target_source = f"upstream:{bottleneck_parent or 'unknown'}"
                else:
                    effective_latency_target_ms = latency_slo_ms
                    effective_latency_target_source = (
                        f"local_slo_fallback_no_healthy_p90;"
                        f"upstream:{bottleneck_parent or 'unknown'}"
                    )

            wq_allowed_s = max(0.001, (effective_latency_target_ms / 1000.0) - S_s)

            p_wait_current = erlang_c(lambda_rps, mu, pods_count)
            wq_model_current_s_avg = expected_queueing_delay(lambda_rps, mu, pods_count)
            #print("expecte")
            wq_model_current_s = waiting_percentile_mmc(lambda_rps, mu, pods_count, queue_tail_quantile)
            wq_model_current_s_ggc = k_variability * wq_model_current_s if math.isfinite(wq_model_current_s) else wq_model_current_s

            # Method 3 now uses calibrated G/G/c-like selected-tail queue delay:
            # S + k * Wq_tail_MMc <= SLO
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

            p_wait_display = f"{p_wait_current:.4f}" if math.isfinite(p_wait_current) else "nan"
            wq_model_display_s = (
                wq_model_current_s if math.isfinite(wq_model_current_s)
                else float("inf") if wq_model_current_s == float("inf") else float("nan")
            )
            wq_model_display_s_avg = (
                wq_model_current_s_avg if math.isfinite(wq_model_current_s_avg)
                else float("inf") if wq_model_current_s_avg == float("inf") else float("nan")
            )

            wq_model_display_s_ggc = (
                wq_model_current_s_ggc if math.isfinite(wq_model_current_s_ggc)
                else float("inf") if wq_model_current_s_ggc == float("inf") else float("nan")
            )

            #############
            # Logging Execution Blocks
            #############
            logging.info(
                "\n"
                "==================== DAS STATE ====================\n"
                f"[Service] {deployment} | Topology Node Type: {node_type}\n"
                "\n"
                "[Load & Capacity Context]\n"
                f"  λ (arrival rate)        : {lambda_rps:.2f} req/s\n"
                f"  Replicas (c)            : {pods_count}\n"
                f"  Capacity (c·μ)          : {(pods_count * mu):.2f} req/s\n"
                "\n"
                "[Latency Framework Context]\n"
                f"  P25 (processing proxy)  : {R_p25_ms:.2f} ms\n"
                f"  P50 (baseline transit)  : {R_p50_ms:.2f} ms\n"
                f"  P90 (observed transit)  : {R_p90_ms:.2f} ms\n"
                f"  {slo_tail_label} (selected SLO tail): {R_slo_ms:.2f} ms\n"
                f"  Healthy P90 target     : {(own_healthy_p90_target_ms if own_healthy_p90_target_ms is not None else float('nan')):.2f} ms "
                f"(P25 of recent healthy P90, n={len(healthy_self_p90_history_ms)})\n"
                "\n"
                "[Service-Time Modeling]\n"
                f"  Processing time S : {S_s * 1000:.2f} ms\n"
                f"  Source                  : {service_time_source}\n"
                f"  Observed {slo_tail_label} Excess Delay      : {observed_tail_excess_s * 1000:.2f} ms  ({slo_tail_label} - S)\n"
                f"  Modelled Mean Queue Delay     : {wq_model_display_s_avg * 1000:.2f} ms\n"
                f"  Modelled {queue_tail_label} Queue Delay MMC  : {wq_model_display_s * 1000:.2f} ms\n"
                f"  Variability factor k          : {k_variability:.3f}\n"
                f"  Modelled {queue_tail_label} Queue Delay GGC  : {wq_model_display_s_ggc * 1000:.2f} ms\n"
                f"  Effective {slo_tail_label} Target          : {effective_latency_target_ms:.2f} ms ({effective_latency_target_source})\n"
                f"  Queue Budget              : {wq_allowed_s * 1000:.2f} ms\n"
                f"  Queue ratio (excess/{slo_tail_label})      : {(observed_tail_excess_s / R_slo_s if R_slo_s > 0 else 0):.2f}\n"
                "\n"
                "[Resource Boundaries]\n"
                f"  ρ (local utilisation)   : {rho:.2f}\n"
                f"  Status                  : "
                f"{'OVERLOADED 🔴' if rho >= 1 else 'HIGH 🟠' if rho > 0.8 else 'OK 🟢'}\n"
                "\n"
                "[Replica Calculation Results]\n"
                f"  Method 1: Queueing Recom: {recommended_replicas} (delta: {recommended_replicas - pods_count:+d})\n"
                f"  Method 2: HPA CPU Recom : {hpa_recommended} (not used, delta: {hpa_recommended - pods_count:+d})\n"
                f"  Method 3a: {queue_tail_label}-SLO MMC Recom: {slo_recommended_mmc} (delta: {slo_recommended_mmc - pods_count:+d})\n"
                f"  Method 3b: {queue_tail_label}-SLO GGC Recom: {slo_recommended} (delta: {slo_recommended - pods_count:+d})\n"
                "===================================================\n"
            )

            logging.info(
                build_deployment_monitoring_log(
                    deployment=deployment, cpu_m=cpu_m, mem_mib=mem_mib, pods_count=pods_count,
                    cpu_utilisation=cpu_utilisation, mem_utilisation=mem_utilisation,
                    http_rpm_as_dst=http_rpm_as_dst, grpc_rpm_as_dst=grpc_rpm_as_dst,
                    http_latency_p50_as_dst=http_latency_p50_as_dst, grpc_latency_p50_as_dst=grpc_latency_p50_as_dst,
                    http_latency_p90_as_dst=http_latency_p90_as_dst, grpc_latency_p90_as_dst=grpc_latency_p90_as_dst,
                    http_latency_p95_as_dst=http_latency_p95_as_dst, grpc_latency_p95_as_dst=grpc_latency_p95_as_dst,
                    http_rpm_as_src=http_rpm_as_src, grpc_rpm_as_src=grpc_rpm_as_src,
                    http_latency_p50_as_src=http_latency_p50_as_src, grpc_latency_p50_as_src=grpc_latency_p50_as_src,
                    http_latency_p90_as_src=http_latency_p90_as_src, grpc_latency_p90_as_src=grpc_latency_p90_as_src,
                    http_latency_p95_as_src=http_latency_p95_as_src, grpc_latency_p95_as_src=grpc_latency_p95_as_src,
                    http_rpm_mesh_as_dst=http_rpm_mesh_as_dst, grpc_rpm_mesh_as_dst=grpc_rpm_mesh_as_dst,
                    http_latency_mesh_avg_as_dst=http_latency_mesh_avg_as_dst, grpc_latency_mesh_avg_as_dst=grpc_latency_mesh_avg_as_dst,
                    http_latency_p95_mesh_as_dst=http_latency_p95_mesh_as_dst, grpc_latency_p95_mesh_as_dst=grpc_latency_p95_mesh_as_dst,
                    http_latency_p90_mesh_as_dst=http_latency_p90_mesh_as_dst, grpc_latency_p90_mesh_as_dst=grpc_latency_p90_mesh_as_dst,
                    http_rpm_mesh_as_src=http_rpm_mesh_as_src, grpc_rpm_mesh_as_src=grpc_rpm_mesh_as_src,
                    http_latency_mesh_avg_as_src=http_latency_mesh_avg_as_src, grpc_latency_mesh_avg_as_src=grpc_latency_mesh_avg_as_src,
                    http_latency_p95_mesh_as_src=http_latency_p95_mesh_as_src, grpc_latency_p95_mesh_as_src=grpc_latency_p95_mesh_as_src,
                    http_latency_p90_mesh_as_src=http_latency_p90_mesh_as_src, grpc_latency_p90_mesh_as_src=grpc_latency_p90_mesh_as_src,
                    upstreams=upstreams, downstreams=downstreams,
                    selected_tail_label=slo_tail_label,
                )
            )

            #############
            # Step 3.5: Reactive Bottleneck-Aware Diagnosis
            #############
            selected_mesh_src = merge_dict_metric(http_latency_p90_mesh_as_src, grpc_latency_p90_mesh_as_src) if slo_tail_label == "P90" else merge_dict_metric(http_latency_p95_mesh_as_src, grpc_latency_p95_mesh_as_src)

            # Healthy baseline recording is based on SLO/bottleneck state only.
            # Do not gate healthy selected-tail/ratio histories by rho: these histories
            # represent acceptable online operating envelopes, not queue-free
            # service-time estimates.

            frontend_slo_violated = deployment in ROOT_SERVICES and R_slo_ms > latency_slo_ms
            bottleneck_candidates: list[dict[str, Any]] = []
            scale_reason = "hold"
            desired_replicas_bottleneck = pods_count

            if deployment in ROOT_SERVICES:
                if not frontend_slo_violated:
                    # Healthy P90 guideline learning is already performed before
                    # replica recommendation using update_healthy_p90_guideline().
                    logging.info(
                        "[SELF HEALTH STATUS] service=%s tail=%s value=%.2fms healthy_p25_p90=%.2fms samples=%d frontend_slo_violated=%s",
                        deployment,
                        slo_tail_label,
                        R_slo_ms,
                        own_healthy_p90_target_ms if own_healthy_p90_target_ms is not None else float("nan"),
                        len(healthy_self_p90_history_ms),
                        frontend_slo_violated,
                    )
                    update_normal_downstream_thresholds(normal_downstream_tail_history_ms, selected_mesh_src, healthy_threshold_max_samples)
                    update_normal_downstream_ratio_thresholds(normal_downstream_ratio_history, R_slo_ms, selected_mesh_src, healthy_threshold_max_samples)
                    scale_reason = "frontend_slo_ok_update_thresholds"
                else:
                    bottleneck_candidates = detect_downstream_bottlenecks(
                        upstream_source_tail_ms=R_source_slo_ms,
                        self_tail_ms=R_slo_ms,
                        downstream_tail_ms=selected_mesh_src,
                        threshold_history_ms=normal_downstream_tail_history_ms,
                        ratio_history=normal_downstream_ratio_history,
                        require_source_dominance=True,
                        tail_label=slo_tail_label,
                    )
                    if bottleneck_candidates:
                        for b in bottleneck_candidates:
                            logging.info(
                                "[BOTTLENECK DETECTED] parent=%s child=%s current_%s=%.2fms source_%s=%.2fms healthy_selected_target=%.2fms healthy_mean=%.2fms healthy_n=%s allowed_%s=%.2fms reason=%s",
                                deployment,
                                b["service"],
                                slo_tail_label.lower(),
                                metric_value(b, "current", slo_tail_label),
                                slo_tail_label.lower(),
                                metric_value(b, "upstream_source", slo_tail_label),
                                metric_value(b, "threshold", slo_tail_label),
                                metric_value(b, "healthy_mean", slo_tail_label),
                                b.get("healthy_sample_count", 0),
                                slo_tail_label.lower(),
                                metric_value(b, "allowed", slo_tail_label),
                                b["reason"],
                            )
                            send_bottleneck_alert(
                                p2p_agent=p2p_agent,
                                target=b["service"],
                                parent=deployment,
                                allowed_tail_ms=b["allowed_tail_ms"],
                                current_tail_ms=b["current_tail_ms"],
                                reason=b["reason"],
                                tail_label=slo_tail_label,
                            )
                        scale_reason = "frontend_slo_violated_forwarded_to_downstream"
                    else:
                        # Non-leaf/root fallback: if the frontend SLO is violated
                        # but no downstream bottleneck is identified, scale this
                        # node using the M/M/c SLO replica recommendation.
                        desired_replicas_bottleneck = slo_recommended_mmc
                        scale_reason = "frontend_slo_violated_no_downstream_bottleneck_scale_self_mmc"
                        logging.info(
                            "[BOTTLENECK FALLBACK] service=%s node_type=%s using_mmc_recommendation=%d current=%d cpu_util=%.2f%% reason=%s",
                            deployment,
                            node_type,
                            slo_recommended_mmc,
                            pods_count,
                            cpu_utilisation,
                            scale_reason,
                        )

            else:
                if not received_bottleneck:
                    # Healthy P90 guideline learning is already performed before
                    # replica recommendation using update_healthy_p90_guideline().
                    logging.info(
                        "[SELF HEALTH STATUS] service=%s tail=%s value=%.2fms healthy_p25_p90=%.2fms samples=%d received_pressure=%s",
                        deployment,
                        slo_tail_label,
                        R_slo_ms,
                        own_healthy_p90_target_ms if own_healthy_p90_target_ms is not None else float("nan"),
                        len(healthy_self_p90_history_ms),
                        received_bottleneck,
                    )
                    update_normal_downstream_thresholds(normal_downstream_tail_history_ms, selected_mesh_src, healthy_threshold_max_samples)
                    update_normal_downstream_ratio_thresholds(normal_downstream_ratio_history, R_slo_ms, selected_mesh_src, healthy_threshold_max_samples)
                    scale_reason = "no_bottleneck_msg_update_thresholds"
                else:
                    if node_type == "leaf":
                        # We can try CPU based
                        desired_replicas_bottleneck = recommend_replicas_for_target_tail_mmc(
                            lambda_rps=lambda_rps,
                            mu=mu,
                            target_tail_ms=effective_latency_target_ms,
                            service_time_s=S_s,
                            min_replicas=min_replicas,
                            max_replicas=max_replicas,
                            current_replicas=pods_count,
                            queue_percentile=queue_tail_quantile,
                        )
                        scale_reason = f"leaf_received_pressure_scale_self_mmc_to_{effective_latency_target_source}_{slo_tail_label.lower()}"
                    else:
                        valid_children = {
                            child: tail
                            for child, tail in selected_mesh_src.items()
                            if child not in EXTERNAL_UPSTREAMS
                            and child not in (None, "")
                            and valid_number(tail)
                            and tail > 0
                        }

                        if len(valid_children) == 1:
                            child, child_tail = next(iter(valid_children.items()))

                            child_allowed = threshold_snapshot_ms(
                                normal_downstream_tail_history_ms,
                                bottleneck_healthy_stat,
                            ).get(child)

                            ratio_stats = healthy_ratio_stats_snapshot(
                                normal_downstream_ratio_history
                            ).get(child, {})

                            healthy_ratio_mean = ratio_stats.get("mean")
                            healthy_ratio_median = ratio_stats.get("median", float("nan"))
                            healthy_ratio_selected = ratio_stats.get(bottleneck_healthy_stat)
                            healthy_ratio_n = int(ratio_stats.get("count", 0))

                            child_ratio = (
                                child_tail / R_slo_ms
                                if valid_number(R_slo_ms) and R_slo_ms > 0
                                else float("nan")
                            )

                            has_healthy_single_child_info = (
                                child_allowed is not None
                                and valid_number(child_allowed)
                                and child_allowed > 0
                                and healthy_ratio_selected is not None
                                and valid_number(healthy_ratio_selected)
                                and healthy_ratio_selected > 0
                            )

                            child_exceeds_healthy_baseline = (
                                has_healthy_single_child_info
                                and child_tail > child_allowed
                            )

                            child_exceeds_healthy_ratio_baseline = (
                                has_healthy_single_child_info
                                and valid_number(child_ratio)
                                and child_ratio > healthy_ratio_selected
                            )

                            if has_healthy_single_child_info:
                                child_is_bottleneck = (
                                    child_exceeds_healthy_baseline
                                    and child_exceeds_healthy_ratio_baseline
                                )
                                single_child_reason = f"single_child_exceeds_healthy_{bottleneck_healthy_stat}_and_ratio_{bottleneck_healthy_stat}"
                                child_allowed_for_alert = child_allowed
                            else:
                                child_is_bottleneck = (
                                    valid_number(child_ratio)
                                    and child_ratio > single_child_forward_fraction
                                )
                                single_child_reason = "cold_start_single_child_ratio_gt_0_5"
                                child_allowed_for_alert = (
                                    received_allowed_tail_ms
                                    if received_allowed_tail_ms is not None
                                    and valid_number(received_allowed_tail_ms)
                                    and received_allowed_tail_ms > 0
                                    else R_slo_ms
                                )

                            self_exceeds_upstream_target = (
                                received_allowed_tail_ms is not None
                                and valid_number(received_allowed_tail_ms)
                                and R_slo_ms > received_allowed_tail_ms
                            )

                            child_allowed_display = (
                                float(child_allowed)
                                if child_allowed is not None and valid_number(child_allowed)
                                else float("nan")
                            )

                            healthy_ratio_mean_display = (
                                float(healthy_ratio_mean)
                                if healthy_ratio_mean is not None and valid_number(healthy_ratio_mean)
                                else float("nan")
                            )

                            logging.info(
                                "[SINGLE CHILD ANALYSIS] parent=%s child=%s parent_%s=%.2fms child_%s=%.2fms "
                                "current_ratio=%.3f healthy_ratio_mean=%.3f healthy_ratio_median=%.3f ratio_n=%d "
                                "healthy_selected_target=%.2fms has_healthy_info=%s child_exceeds_%s=%s "
                                "child_exceeds_ratio=%s child_is_bottleneck=%s upstream_target_%s=%.2fms "
                                "self_exceeds_target=%s reason=%s",
                                deployment,
                                child,
                                slo_tail_label.lower(),
                                R_slo_ms,
                                slo_tail_label.lower(),
                                child_tail,
                                child_ratio,
                                healthy_ratio_mean_display,
                                healthy_ratio_median if valid_number(healthy_ratio_median) else float("nan"),
                                healthy_ratio_n,
                                child_allowed_display,
                                has_healthy_single_child_info,
                                slo_tail_label.lower(),
                                child_exceeds_healthy_baseline,
                                child_exceeds_healthy_ratio_baseline,
                                child_is_bottleneck,
                                slo_tail_label.lower(),
                                effective_latency_target_ms,
                                self_exceeds_upstream_target,
                                single_child_reason if child_is_bottleneck else "-",
                            )

                            if child_is_bottleneck:
                                logging.info(
                                    "[BOTTLENECK FORWARD] parent=%s child=%s current_%s=%.2fms "
                                    "current_ratio=%.3f allowed_%s=%.2fms reason=%s upstream_target_%s=%.2fms",
                                    deployment,
                                    child,
                                    slo_tail_label.lower(),
                                    child_tail,
                                    child_ratio,
                                    slo_tail_label.lower(),
                                    child_allowed_for_alert,
                                    single_child_reason,
                                    slo_tail_label.lower(),
                                    effective_latency_target_ms,
                                )

                                send_bottleneck_alert(
                                    p2p_agent=p2p_agent,
                                    target=child,
                                    parent=deployment,
                                    allowed_tail_ms=child_allowed_for_alert,
                                    current_tail_ms=child_tail,
                                    reason=single_child_reason,
                                    tail_label=slo_tail_label,
                                )

                                tail_stats = healthy_tail_stats_snapshot_ms(
                                    normal_downstream_tail_history_ms
                                ).get(child, {})
                                metric_key = tail_metric_key(slo_tail_label)
                                bottleneck_candidates = [{
                                    "service": child,
                                    "tail_label": slo_tail_label,
                                    "current_tail_ms": float(child_tail),
                                    "upstream_source_tail_ms": float(R_source_slo_ms) if valid_number(R_source_slo_ms) else float("nan"),
                                    "self_tail_ms": float(R_slo_ms),
                                    f"current_{metric_key}_ms": float(child_tail),
                                    f"upstream_source_{metric_key}_ms": float(R_source_slo_ms) if valid_number(R_source_slo_ms) else float("nan"),
                                    f"self_{metric_key}_ms": float(R_slo_ms),
                                    "current_ratio": float(child_ratio) if valid_number(child_ratio) else float("nan"),
                                    "healthy_ratio_mean": float(healthy_ratio_mean_display),
                                    "healthy_ratio_median": float(healthy_ratio_median) if valid_number(healthy_ratio_median) else float("nan"),
                                    "healthy_ratio_sample_count": healthy_ratio_n,
                                    "healthy_ratio_selected": float(healthy_ratio_selected) if valid_number(healthy_ratio_selected) else float("nan"),
                                    "healthy_stat_mode": bottleneck_healthy_stat,
                                    "threshold_tail_ms": float(child_allowed) if valid_number(child_allowed) else float("nan"),
                                    "healthy_selected_tail_ms": float(child_allowed) if valid_number(child_allowed) else float("nan"),
                                    "healthy_p25_tail_ms": float(tail_stats.get("p25", float("nan"))) if valid_number(tail_stats.get("p25", float("nan"))) else float("nan"),
                                    "healthy_mean_tail_ms": float(tail_stats.get("mean", float("nan"))) if valid_number(tail_stats.get("mean", float("nan"))) else float("nan"),
                                    "healthy_median_tail_ms": float(tail_stats.get("median", float("nan"))) if valid_number(tail_stats.get("median", float("nan"))) else float("nan"),
                                    f"threshold_{metric_key}_ms": float(child_allowed) if valid_number(child_allowed) else float("nan"),
                                    f"healthy_selected_{metric_key}_ms": float(child_allowed) if valid_number(child_allowed) else float("nan"),
                                    f"healthy_p25_{metric_key}_ms": float(tail_stats.get("p25", float("nan"))) if valid_number(tail_stats.get("p25", float("nan"))) else float("nan"),
                                    f"healthy_mean_{metric_key}_ms": float(tail_stats.get("mean", float("nan"))) if valid_number(tail_stats.get("mean", float("nan"))) else float("nan"),
                                    f"healthy_median_{metric_key}_ms": float(tail_stats.get("median", float("nan"))) if valid_number(tail_stats.get("median", float("nan"))) else float("nan"),
                                    "healthy_sample_count": int(tail_stats.get("count", 0)),
                                    "allowed_tail_ms": float(child_allowed_for_alert),
                                    f"allowed_{metric_key}_ms": float(child_allowed_for_alert),
                                    "reason": single_child_reason,
                                }]

                                scale_reason = "single_child_bottleneck_forwarded_only"

                            elif self_exceeds_upstream_target:
                                # Non-leaf/intermediate fallback: no child is judged
                                # as the bottleneck, so scale this node using the
                                # M/M/c SLO replica recommendation, not HPA.
                                desired_replicas_bottleneck = slo_recommended_mmc
                                scale_reason = "single_child_no_child_bottleneck_scale_self_mmc"
                                logging.info(
                                    "[BOTTLENECK FALLBACK] service=%s node_type=%s child=%s using_mmc_recommendation=%d current=%d cpu_util=%.2f%% upstream_target=%.2fms reason=%s",
                                    deployment,
                                    node_type,
                                    child,
                                    slo_recommended_mmc,
                                    pods_count,
                                    cpu_utilisation,
                                    effective_latency_target_ms,
                                    scale_reason,
                                )

                            else:
                                scale_reason = "single_child_no_child_bottleneck_self_ok_hold"
                        else:
                            bottleneck_candidates = detect_downstream_bottlenecks(
                                upstream_source_tail_ms=R_source_slo_ms,
                                self_tail_ms=R_slo_ms,
                                downstream_tail_ms=selected_mesh_src,
                                threshold_history_ms=normal_downstream_tail_history_ms,
                                ratio_history=normal_downstream_ratio_history,
                                require_source_dominance=True,
                                parent_target_tail_ms=received_allowed_tail_ms,
                                tail_label=slo_tail_label,
                            )

                            if bottleneck_candidates:
                                for b in bottleneck_candidates:
                                    logging.info(
                                        "[BOTTLENECK FORWARD] parent=%s child=%s current_%s=%.2fms source_%s=%.2fms healthy_selected_target=%.2fms healthy_mean=%.2fms healthy_n=%s allowed_%s=%.2fms reason=%s upstream_target_%s=%.2fms",
                                        deployment,
                                        b["service"],
                                        slo_tail_label.lower(),
                                        metric_value(b, "current", slo_tail_label),
                                        slo_tail_label.lower(),
                                        metric_value(b, "upstream_source", slo_tail_label),
                                        metric_value(b, "threshold", slo_tail_label),
                                        metric_value(b, "healthy_mean", slo_tail_label),
                                        b.get("healthy_sample_count", 0),
                                        slo_tail_label.lower(),
                                        metric_value(b, "allowed", slo_tail_label),
                                        b["reason"],
                                        slo_tail_label.lower(),
                                        effective_latency_target_ms,
                                    )
                                    send_bottleneck_alert(
                                        p2p_agent=p2p_agent,
                                        target=b["service"],
                                        parent=deployment,
                                        allowed_tail_ms=b["allowed_tail_ms"],
                                        current_tail_ms=b["current_tail_ms"],
                                        reason=b["reason"],
                                        tail_label=slo_tail_label,
                                    )
                                # If at least one child is a bottleneck, forward only.
                                # The intermediate scales itself only when no child bottleneck
                                # is detected.
                                scale_reason = "received_bottleneck_forwarded_to_downstream"
                            else:
                                # Non-leaf/intermediate fallback: if an upstream
                                # reports a bottleneck but no downstream child is
                                # identified as the bottleneck, scale this service
                                # using the M/M/c SLO replica recommendation, not HPA.
                                desired_replicas_bottleneck = slo_recommended_mmc
                                scale_reason = "received_bottleneck_no_downstream_bottleneck_scale_self_mmc"
                                logging.info(
                                    "[BOTTLENECK FALLBACK] service=%s node_type=%s using_mmc_recommendation=%d current=%d cpu_util=%.2f%% upstream_target=%.2fms reason=%s",
                                    deployment,
                                    node_type,
                                    slo_recommended_mmc,
                                    pods_count,
                                    cpu_utilisation,
                                    effective_latency_target_ms,
                                    scale_reason,
                                )

            # Root/frontend broadcasts global SLO violation to ALL downstream services.
            # Each downstream then scales using its own P25(recent healthy P90) target.
            if node_type == "root" and frontend_slo_violated:
                for downstream in downstreams:
                    if downstream in EXTERNAL_UPSTREAMS or downstream in (None, ""):
                        continue
                    sent = send_frontend_slo_violation_broadcast(
                        p2p_agent=p2p_agent,
                        target=downstream,
                        parent=deployment,
                        frontend_tail_ms=R_slo_ms,
                        frontend_slo_ms=latency_slo_ms,
                        tail_label=slo_tail_label,
                    )
                    logging.info(
                        "[FRONTEND SLO BROADCAST] parent=%s target=%s sent=%s frontend_%s=%.2fms slo=%.2fms",
                        deployment,
                        downstream,
                        sent,
                        slo_tail_label.lower(),
                        R_slo_ms,
                        latency_slo_ms,
                    )

            # Root/frontend initiates bottleneck propagation. When the frontend detects
            # downstream bottlenecks, it sends MSG_BOTTLENECK_ALERT to those services.
            if node_type == "root" and bottleneck_candidates:
                for bottleneck in bottleneck_candidates:
                    target_service = bottleneck.get("service")
                    if not target_service or target_service in EXTERNAL_UPSTREAMS:
                        continue
                    allowed_for_child = float(bottleneck.get("allowed_tail_ms", effective_latency_target_ms))
                    observed_for_child = float(bottleneck.get("current_tail_ms", float("nan")))
                    sent = send_bottleneck_alert(
                        p2p_agent=p2p_agent,
                        target=target_service,
                        parent=deployment,
                        allowed_tail_ms=allowed_for_child,
                        current_tail_ms=observed_for_child,
                        reason=f"ROOT FRONTEND BOTTLENECK FORWARD: {bottleneck.get('reason', 'frontend_detected_bottleneck')}",
                        tail_label=slo_tail_label,
                    )
                    logging.info(
                        "[BOTTLENECK FORWARD] parent=%s target=%s sent=%s allowed_%s=%.2fms observed_%s=%.2fms reason=%s",
                        deployment,
                        target_service,
                        sent,
                        slo_tail_label.lower(),
                        allowed_for_child,
                        slo_tail_label.lower(),
                        observed_for_child,
                        bottleneck.get("reason", "frontend_detected_bottleneck"),
                    )

            logging.info(
                build_bottleneck_diagnosis_table(
                    deployment=deployment,
                    node_type=node_type,
                    frontend_slo_violated=frontend_slo_violated,
                    received_bottleneck=received_bottleneck,
                    received_allowed_tail_ms=received_allowed_tail_ms,
                    bottleneck_parent=bottleneck_parent,
                    upstream_source_tail_ms=R_source_slo_ms,
                    self_tail_ms=R_slo_ms,
                    downstream_tail_ms=selected_mesh_src,
                    threshold_history_ms=normal_downstream_tail_history_ms,
                    ratio_history=normal_downstream_ratio_history,
                    bottleneck_candidates=bottleneck_candidates,
                    tail_label=slo_tail_label,
                )
            )

            logging.info(
                "[BOTTLENECK DECISION] service=%s reason=%s desired=%d current=%d delta=%+d",
                deployment,
                scale_reason,
                desired_replicas_bottleneck,
                pods_count,
                desired_replicas_bottleneck - pods_count,
            )

            #############
            # Step 4: Directional Execution Cooldown Routing
            #############
            # Reactive bottleneck-aware scaling is conservative: only scale up during
            # bottleneck relief. Scale-down can be handled by a separate policy later.
            raw_delta_replicas = max(0, desired_replicas_bottleneck - pods_count)
            delta_replicas = min(raw_delta_replicas, max_scale_up_step)

            if raw_delta_replicas > max_scale_up_step:
                logging.info(
                    "[SCALE UP CAP] %s requested_delta=%d capped_delta=%d max_scale_up_step=%d desired=%d current=%d",
                    deployment,
                    raw_delta_replicas,
                    delta_replicas,
                    max_scale_up_step,
                    desired_replicas_bottleneck,
                    pods_count,
                )

            if delta_replicas > 0:
                scale_down_ok_windows = 0
                if now - last_scale_up_time < scale_up_cooldown:
                    logging.info("[COOLDOWN HOLD] Scale-Up request throttled. Elapsed: %.1fs | Required Target: %.1fs",
                                 now - last_scale_up_time, scale_up_cooldown)
                    wait_for_next_loop(interval)
                    continue

                result = executor.scale_by(deployment, delta=delta_replicas, min_replicas=min_replicas, max_replicas=max_replicas)
                last_scale_up_time = now
                logging.info(
                    "[SCALE UP ACTION] %s scaling delta=%d executed. raw_delta=%d desired=%d current=%d Result=%s",
                    deployment,
                    delta_replicas,
                    raw_delta_replicas,
                    desired_replicas_bottleneck,
                    pods_count,
                    result,
                )
            else:
                logging.info("[HOLD] %s no reactive bottleneck-aware scale-up required. reason=%s", deployment, scale_reason)

                # Conservative local scale-down:
                # Try removing one replica. If modeled selected-tail latency with c-1
                # stays below this service's own healthy selected-tail baseline P25
                # for enough consecutive windows, scale down. The upstream-sent
                # allowed tail target is used for temporary scale-up pressure only,
                # not as this service's downscale baseline.
                healthy_self_target_ms = healthy_stat(healthy_self_p90_history_ms, bottleneck_healthy_stat)
                local_scale_down_target_ms = (
                    min(latency_slo_ms, healthy_self_target_ms)
                    if healthy_self_target_ms is not None and valid_number(healthy_self_target_ms)
                    else None
                )
                candidate_replicas = pods_count - scale_down_step
                predicted_tail_down_ms = (
                    predict_tail_mmc_ms(lambda_rps, mu, candidate_replicas, S_s, queue_tail_quantile)
                    if candidate_replicas >= min_replicas
                    else float("nan")
                )
                required_windows = required_scale_down_windows(recent_bottleneck_count_by_parent)
                scale_down_safe = (
                    local_scale_down_target_ms is not None
                    and valid_number(local_scale_down_target_ms)
                    and candidate_replicas >= min_replicas
                    and math.isfinite(predicted_tail_down_ms)
                    and predicted_tail_down_ms <= local_scale_down_target_ms
                    and not received_bottleneck
                    and not frontend_slo_violated
                    and not bottleneck_candidates
                )

                if scale_down_safe:
                    scale_down_ok_windows += 1
                else:
                    scale_down_ok_windows = 0

                logging.info(
                    "[SCALE DOWN CHECK] service=%s candidate=%s current=%d predicted_%s=%.2fms healthy_%s_%s=%s local_slo=%.2fms target_%s=%s samples=%d ok_windows=%d required_windows=%d bottleneck_memory=%s safe=%s",
                    deployment,
                    candidate_replicas if candidate_replicas >= min_replicas else "below_min",
                    pods_count,
                    queue_tail_label.lower(),
                    predicted_tail_down_ms,
                    bottleneck_healthy_stat,
                    slo_tail_label.lower(),
                    f"{healthy_self_target_ms:.2f}ms" if healthy_self_target_ms is not None else "None",
                    latency_slo_ms,
                    slo_tail_label.lower(),
                    f"{local_scale_down_target_ms:.2f}ms" if local_scale_down_target_ms is not None else "None",
                    len(healthy_self_p90_history_ms),
                    scale_down_ok_windows,
                    required_windows,
                    recent_bottleneck_count_by_parent,
                    scale_down_safe,
                )

                if scale_down_safe and scale_down_ok_windows >= required_windows:
                    if now - last_scale_down_time < scale_down_cooldown:
                        logging.info(
                            "[COOLDOWN HOLD] Scale-Down request throttled. Elapsed: %.1fs | Required Target: %.1fs",
                            now - last_scale_down_time,
                            scale_down_cooldown,
                        )
                    else:
                        result = executor.scale_by(
                            deployment,
                            delta=-scale_down_step,
                            min_replicas=min_replicas,
                            max_replicas=max_replicas,
                        )
                        last_scale_down_time = now
                        scale_down_ok_windows = 0
                        decay_bottleneck_memory_after_downscale(recent_bottleneck_count_by_parent)
                        logging.info(
                            "[SCALE DOWN ACTION] %s scaling delta=-%d executed. candidate=%d predicted_%s=%.2fms healthy_%s_%s=%.2fms target_%s=%.2fms new_bottleneck_memory=%s Result=%s",
                            deployment,
                            scale_down_step,
                            candidate_replicas,
                            queue_tail_label.lower(),
                            predicted_tail_down_ms,
                            bottleneck_healthy_stat,
                            slo_tail_label.lower(),
                            healthy_self_target_ms,
                            slo_tail_label.lower(),
                            local_scale_down_target_ms,
                            recent_bottleneck_count_by_parent,
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
    
    # Decouple configuration sources
    scale_up_cooldown = float(os.getenv("SCALE_UP_COOLDOWN_SECONDS", "30"))
    scale_down_cooldown = float(os.getenv("SCALE_DOWN_COOLDOWN_SECONDS", "180"))
    
    namespace = os.getenv("NAMESPACE", "default")
    deployment = os.getenv("TARGET_DEPLOYMENT", "productpage-v1")
    prom_url = os.getenv("PROM_URL", "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query")
    min_replicas = int(os.getenv("MIN_REPLICAS", "1"))
    max_replicas = int(os.getenv("MAX_REPLICAS", "10"))

    monitor = Monitor(namespace=namespace, prom_url=prom_url)
    executor = Executor(namespace=namespace)

    p2p_agent = P2PAgent()
    p2p_agent.init_peer()

    das_thread = threading.Thread(
        target=das_loop,
        args=(
            monitor, executor, p2p_agent, deployment, interval,
            scale_up_cooldown, scale_down_cooldown, min_replicas, max_replicas,
        ),
        name=f"das-loop-{deployment}",
        daemon=True,
    )
    das_thread.start()
    p2p_agent.start()


if __name__ == "__main__":
    main()
