from __future__ import annotations

"""HAB scheduler for Online Boutique.

HAB Algorithm 2 (Auto-scaling Decision), using the fixed
Online Boutique calibration:

    N(lambda) = (lambda / lambda_base) * phi_base * p

Algorithm 1 (phi_base measurement) is intentionally not implemented here,
because lambda_base, phi_base and the fixed p vector are supplied as calibrated
inputs.
Calibarating process:
    1. set a base lambda (139 rps measured, 300 rps from workloads)
    2. find replica sets so that p95 is 450
    3. record cpu usage
    4. collect p vector (simply use request aware cpu usage since their model use utilisation as metric)
    5. calculate phi value using replica counts and p vector

Runtime behavior:
  1. Monitor root-service workload lambda and root latency R.
  2. If R is inside [R_LOW_MS, R_UP_MS], hold.
  3. If R is outside the band, compute proportional HAB vector N.
  4. If N differs from current replicas, scale all services to N.
  5. After proportional scaling, wait for the new replica vector to stabilize;
     then, if R is still outside the band and the request rate has not changed
     much, perform step-by-step exploratory scaling:
       - R > R_UP_MS  : scale up the service with highest CPU utilization.
       - R < R_LOW_MS : scale down the service with lowest CPU utilization.

All important values can be configured via environment variables.
"""

import json
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any

from kubernetes import config

from monitoring import Monitor
from execution import Executor

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---------------------------------------------------------------------------
# Online Boutique HAB defaults
# ---------------------------------------------------------------------------

ONLINE_BOUTIQUE_SERVICES: list[str] = [
    "frontend",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "paymentservice",
    "productcatalogservice",
    "recommendationservice",
    "shippingservice",
    "adservice",
]

# Fixed normalized capacity-aware p vector for Online Boutique.
# This is the shape of the balanced deployment, not a replica count.
# Largest component is currencyservice = 1.0.
DEFAULT_ONLINE_BOUTIQUE_P_VECTOR: dict[str, float] = {
    "currencyservice": 1.00,
    "frontend": 0.63,
    "cartservice": 0.61,
    "recommendationservice": 0.55,
    "productcatalogservice": 0.54,
    "adservice": 0.13,
    "shippingservice": 0.09,
    "checkoutservice": 0.09,
    "emailservice": 0.04,
    "paymentservice": 0.03,
}


@dataclass(frozen=True)
class HABConfig:
    namespace: str
    prom_url: str
    interval: float
    stabilization_seconds: float
    post_proportional_wait_seconds: float
    cooldown_seconds: float
    root_service: str
    services: list[str]
    p_vector: dict[str, float]
    lambda_base_rps: float
    phi_base: float
    r_up_ms: float
    r_low_ms: float
    min_replicas: int
    max_replicas: int
    scale_down_enabled: bool
    exploratory_enabled: bool
    exploratory_max_steps: int
    stable_lambda_rel_delta: float


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_services(value: str | None) -> list[str]:
    if not value:
        return list(ONLINE_BOUTIQUE_SERVICES)
    services = [item.strip() for item in value.split(",") if item.strip()]
    return services or list(ONLINE_BOUTIQUE_SERVICES)


def _parse_p_vector(value: str | None) -> dict[str, float]:
    if not value:
        return dict(DEFAULT_ONLINE_BOUTIQUE_P_VECTOR)

    try:
        parsed: Any = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("P_VECTOR_JSON must be a JSON object")
        vector = {str(k): float(v) for k, v in parsed.items()}
        if not vector:
            raise ValueError("P_VECTOR_JSON is empty")
        return vector
    except Exception as exc:
        logging.warning(
            "Could not parse P_VECTOR_JSON=%r; using default Online Boutique vector: %s",
            value,
            exc,
        )
        return dict(DEFAULT_ONLINE_BOUTIQUE_P_VECTOR)


def load_config() -> HABConfig:
    namespace = os.getenv("NAMESPACE", "default")
    prom_url = os.getenv(
        "PROM_URL",
        "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    )

    services = _parse_services(os.getenv("HAB_SERVICES") or os.getenv("DEPLOYMENT_NAMES"))
    p_vector = _parse_p_vector(os.getenv("P_VECTOR_JSON"))

    missing = [svc for svc in services if svc not in p_vector]
    if missing:
        raise ValueError(
            "Missing p-vector entries for services: " + ", ".join(sorted(missing))
        )

    interval = float(os.getenv("INTERVAL", "15"))

    return HABConfig(
        namespace=namespace,
        prom_url=prom_url,
        interval=interval,
        # Wait time between exploratory steps. Also used when line 13-14
        # enters exploratory mode without a preceding proportional scale.
        stabilization_seconds=float(os.getenv("HAB_STABILIZATION_SECONDS", "60")),
        # Wait after applying the proportional HAB vector before checking
        # whether latency is still outside the band and entering exploratory
        # scaling. This avoids reacting to stale pre-scale latency.
        post_proportional_wait_seconds=float(
            os.getenv("HAB_POST_PROPORTIONAL_WAIT_SECONDS", "60")
        ),
        cooldown_seconds=float(os.getenv("COOLDOWN_SECONDS", "30")),
        root_service=os.getenv("ROOT_SERVICE", "frontend"),
        services=services,
        p_vector={svc: float(p_vector[svc]) for svc in services},
        # Calibrated from the monitored Online Boutique base point.
        lambda_base_rps=float(os.getenv("LAMBDA_BASE_RPS", "139.11")),
        phi_base=float(os.getenv("PHI_BASE", "3.37")),
        # Algorithm 2 uses R_up and R_low as the application response-time band.
        r_up_ms=float(os.getenv("R_UP_MS", os.getenv("SLO_MS", "500"))),
        r_low_ms=float(os.getenv("R_LOW_MS", "400")),
        min_replicas=int(os.getenv("MIN_REPLICAS", "1")),
        max_replicas=int(os.getenv("MAX_REPLICAS", "10")),
        scale_down_enabled=_parse_bool(os.getenv("HAB_SCALE_DOWN_ENABLED"), default=True),
        exploratory_enabled=_parse_bool(os.getenv("HAB_EXPLORATORY_ENABLED"), default=True),
        exploratory_max_steps=int(os.getenv("HAB_EXPLORATORY_MAX_STEPS", "3")),
        # Algorithm 2 says exploratory scaling is used when request rate before
        # and after scaling has little change.  This is the relative threshold.
        stable_lambda_rel_delta=float(os.getenv("HAB_STABLE_LAMBDA_REL_DELTA", "0.10")),
    )


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def get_entry_rps(monitor: Monitor, root_service: str) -> float:
    """Entry workload in requests/s."""
    rpm = monitor.get_http_rpm(root_service) + monitor.get_grpc_rpm(root_service)
    return max(rpm / 60.0, 0.0)


def get_root_latency_ms(monitor: Monitor, root_service: str) -> float:
    """Application response time signal R in ms.

    The current monitor API exposes P95 latency. For Online Boutique frontend,
    external traffic is HTTP, but we take max(HTTP, gRPC) defensively.
    """
    http_p95 = monitor.get_http_latency_p95(root_service)
    grpc_p95 = monitor.get_grpc_latency_p95(root_service)
    return max(http_p95, grpc_p95)


def compute_phi(lambda_now_rps: float, lambda_base_rps: float, phi_base: float) -> float:
    if lambda_base_rps <= 0:
        raise ValueError("LAMBDA_BASE_RPS must be > 0")
    return (lambda_now_rps / lambda_base_rps) * phi_base


def compute_desired_replicas(cfg: HABConfig, phi_now: float) -> dict[str, int]:
    desired: dict[str, int] = {}
    for svc in cfg.services:
        raw = math.ceil(phi_now * cfg.p_vector[svc])
        desired[svc] = clamp(raw, cfg.min_replicas, cfg.max_replicas)
    return desired


def get_current_replicas(executor: Executor, services: list[str]) -> dict[str, int]:
    current: dict[str, int] = {}
    for svc in services:
        try:
            current[svc] = executor.get_replicas(svc)
        except Exception:
            logging.exception("Could not read replicas for %s", svc)
            current[svc] = 0
    return current


def is_latency_outside_band(cfg: HABConfig, root_latency_ms: float) -> bool:
    return root_latency_ms > cfg.r_up_ms or root_latency_ms < cfg.r_low_ms


def get_band_reason(cfg: HABConfig, root_latency_ms: float) -> str:
    if root_latency_ms > cfg.r_up_ms:
        return "R_above_R_up"
    if root_latency_ms < cfg.r_low_ms:
        return "R_below_R_low"
    return "R_inside_band"


def is_request_rate_stable(
    before_rps: float,
    after_rps: float,
    rel_threshold: float,
) -> bool:
    denom = max(abs(before_rps), 1e-9)
    rel = abs(after_rps - before_rps) / denom
    return rel <= rel_threshold


def apply_replica_vector(
    *,
    cfg: HABConfig,
    executor: Executor,
    desired: dict[str, int],
    current: dict[str, int],
) -> bool:
    changed = False

    for svc in cfg.services:
        old = current.get(svc, 0)
        new = desired[svc]

        if old == new:
            logging.info("[HAB HOLD SERVICE] %s replicas=%d", svc, old)
            continue

        if new < old and not cfg.scale_down_enabled:
            logging.info(
                "[HAB SKIP SCALE DOWN] %s current=%d desired=%d scale_down_enabled=false",
                svc,
                old,
                new,
            )
            continue

        result = executor.set_replicas(svc, new)
        changed = changed or result.applied
        direction = "UP" if new > old else "DOWN"
        logging.info("[HAB SCALE %s] %s result=%s", direction, svc, result)

    return changed


def get_deployment_cpu_pct(monitor: Monitor, service: str) -> float:
    try:
        return monitor.get_deployment_utilisation(service).cpu_pct
    except Exception:
        logging.exception("Could not read CPU utilisation for %s", service)
        return float("nan")


def choose_exploratory_service(
    *,
    cfg: HABConfig,
    monitor: Monitor,
    executor: Executor,
    scale_up: bool,
) -> tuple[str | None, float]:
    """Choose service for Algorithm 2 step-by-step exploratory scaling.

    If R > R_up, choose the service with the highest CPU utilisation.
    If R < R_low, choose the service with the lowest CPU utilisation among
    deployments that can still be scaled down.
    """
    candidates: list[tuple[str, float]] = []

    for svc in cfg.services:
        replicas = executor.get_replicas(svc)
        if scale_up:
            if replicas >= cfg.max_replicas:
                continue
        else:
            if not cfg.scale_down_enabled or replicas <= cfg.min_replicas:
                continue

        cpu_pct = get_deployment_cpu_pct(monitor, svc)
        if math.isnan(cpu_pct):
            continue
        candidates.append((svc, cpu_pct))

    if not candidates:
        return None, float("nan")

    if scale_up:
        return max(candidates, key=lambda item: item[1])
    return min(candidates, key=lambda item: item[1])


def exploratory_autoscale_once(
    *,
    cfg: HABConfig,
    monitor: Monitor,
    executor: Executor,
    root_latency_ms: float,
) -> bool:
    """Perform one step of HAB Algorithm 2 exploratory auto-scaling."""
    if not cfg.exploratory_enabled:
        logging.info("[HAB EXPLORATORY DISABLED]")
        return False

    if root_latency_ms > cfg.r_up_ms:
        svc, cpu_pct = choose_exploratory_service(
            cfg=cfg,
            monitor=monitor,
            executor=executor,
            scale_up=True,
        )
        if svc is None:
            logging.info("[HAB EXPLORATORY HOLD] no scale-up candidate")
            return False

        current = executor.get_replicas(svc)
        desired = clamp(current + 1, cfg.min_replicas, cfg.max_replicas)
        if desired == current:
            return False
        result = executor.set_replicas(svc, desired)
        logging.info(
            "[HAB EXPLORATORY SCALE UP] service=%s cpu_pct=%.2f R=%.2fms result=%s",
            svc,
            cpu_pct,
            root_latency_ms,
            result,
        )
        return result.applied

    if root_latency_ms < cfg.r_low_ms:
        svc, cpu_pct = choose_exploratory_service(
            cfg=cfg,
            monitor=monitor,
            executor=executor,
            scale_up=False,
        )
        if svc is None:
            logging.info("[HAB EXPLORATORY HOLD] no scale-down candidate")
            return False

        current = executor.get_replicas(svc)
        desired = clamp(current - 1, cfg.min_replicas, cfg.max_replicas)
        if desired == current:
            return False
        result = executor.set_replicas(svc, desired)
        logging.info(
            "[HAB EXPLORATORY SCALE DOWN] service=%s cpu_pct=%.2f R=%.2fms result=%s",
            svc,
            cpu_pct,
            root_latency_ms,
            result,
        )
        return result.applied

    logging.info("[HAB EXPLORATORY HOLD] R inside band")
    return False


def run_exploratory_loop_if_needed(
    *,
    cfg: HABConfig,
    monitor: Monitor,
    executor: Executor,
    lambda_before_rps: float,
    wait_before_first_check_seconds: float,
) -> bool:
    """Run Algorithm 2 lines 8-12 after proportional scaling.

    The first latency sample after proportional scaling is delayed so that
    Kubernetes has time to create/terminate pods and the Prometheus/Istio
    latency window reflects the new deployment rather than the stale pre-scale
    state.

    Continue only while:
      - R remains outside [R_low, R_up], and
      - the request rate before/after scaling has little change.
    """
    any_changed = False
    reference_lambda = lambda_before_rps

    for step in range(1, cfg.exploratory_max_steps + 1):
        wait_seconds = (
            wait_before_first_check_seconds if step == 1 else cfg.stabilization_seconds
        )
        logging.info(
            "[HAB WAIT BEFORE EXPLORATORY CHECK] step=%d/%d wait=%.1fs",
            step,
            cfg.exploratory_max_steps,
            wait_seconds,
        )
        time.sleep(wait_seconds)

        lambda_now = get_entry_rps(monitor, cfg.root_service)
        root_latency = get_root_latency_ms(monitor, cfg.root_service)
        stable = is_request_rate_stable(
            reference_lambda,
            lambda_now,
            cfg.stable_lambda_rel_delta,
        )

        logging.info(
            "[HAB EXPLORATORY CHECK] step=%d/%d lambda_before=%.2f lambda_now=%.2f "
            "stable=%s R=%.2fms band=[%.2f, %.2f]",
            step,
            cfg.exploratory_max_steps,
            reference_lambda,
            lambda_now,
            stable,
            root_latency,
            cfg.r_low_ms,
            cfg.r_up_ms,
        )

        if not is_latency_outside_band(cfg, root_latency):
            logging.info("[HAB EXPLORATORY STOP] R inside band")
            break

        if not stable:
            logging.info("[HAB EXPLORATORY STOP] request rate changed too much")
            break

        changed = exploratory_autoscale_once(
            cfg=cfg,
            monitor=monitor,
            executor=executor,
            root_latency_ms=root_latency,
        )
        any_changed = any_changed or changed

        if not changed:
            logging.info("[HAB EXPLORATORY STOP] no exploratory scaling applied")
            break

        reference_lambda = lambda_now

    return any_changed


def log_hab_state(
    *,
    cfg: HABConfig,
    lambda_now_rps: float,
    root_latency_ms: float,
    phi_now: float,
    current: dict[str, int],
    desired: dict[str, int],
) -> None:
    logging.info("\n==================== HAB ALGORITHM 2 STATE ====================")
    logging.info("Application              : onlineboutique")
    logging.info("Root service             : %s", cfg.root_service)
    logging.info("Entry workload λ         : %.2f req/s", lambda_now_rps)
    logging.info("λ_base                   : %.2f req/s", cfg.lambda_base_rps)
    logging.info("φ_base                   : %.4f", cfg.phi_base)
    logging.info("φ(λ)                     : %.4f", phi_now)
    logging.info(
        "Root P95 latency R       : %.2f ms  target band=[%.2f, %.2f] ms  state=%s",
        root_latency_ms,
        cfg.r_low_ms,
        cfg.r_up_ms,
        get_band_reason(cfg, root_latency_ms),
    )
    logging.info("---------------------------------------------------------------")
    logging.info("Service                  | p_k   | current | proportional N")
    logging.info("---------------------------------------------------------------")
    for svc in cfg.services:
        logging.info(
            "%-24s | %.3f | %7d | %14d",
            svc,
            cfg.p_vector[svc],
            current.get(svc, 0),
            desired[svc],
        )
    logging.info("===============================================================")


def main() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    cfg = load_config()
    monitor = Monitor(namespace=cfg.namespace, prom_url=cfg.prom_url)
    executor = Executor(namespace=cfg.namespace)

    last_scale_time = 0.0

    logging.info(
        "Starting HAB Algorithm 2 scheduler for Online Boutique: root=%s services=%s interval=%.1fs",
        cfg.root_service,
        ",".join(cfg.services),
        cfg.interval,
    )
    logging.info(
        "HAB inputs: lambda_base=%.2f rps phi_base=%.4f R_low=%.2fms R_up=%.2fms "
        "stable_lambda_delta=%.2f exploratory_max_steps=%d post_proportional_wait=%.1fs",
        cfg.lambda_base_rps,
        cfg.phi_base,
        cfg.r_low_ms,
        cfg.r_up_ms,
        cfg.stable_lambda_rel_delta,
        cfg.exploratory_max_steps,
        cfg.post_proportional_wait_seconds,
    )

    while True:
        try:
            now = time.time()

            lambda_now_rps = get_entry_rps(monitor, cfg.root_service)
            root_latency_ms = get_root_latency_ms(monitor, cfg.root_service)
            phi_now = compute_phi(lambda_now_rps, cfg.lambda_base_rps, cfg.phi_base)
            desired = compute_desired_replicas(cfg, phi_now)
            current = get_current_replicas(executor, cfg.services)

            log_hab_state(
                cfg=cfg,
                lambda_now_rps=lambda_now_rps,
                root_latency_ms=root_latency_ms,
                phi_now=phi_now,
                current=current,
                desired=desired,
            )

            # Algorithm 2 outer condition: while R > R_up or R < R_low.
            if not is_latency_outside_band(cfg, root_latency_ms):
                logging.info("[HAB HOLD] R inside [R_low, R_up]; no Algorithm 2 action")
                time.sleep(cfg.interval)
                continue

            if now - last_scale_time < cfg.cooldown_seconds:
                logging.info(
                    "[HAB COOLDOWN] reason=%s elapsed=%.1fs cooldown=%.1fs",
                    get_band_reason(cfg, root_latency_ms),
                    now - last_scale_time,
                    cfg.cooldown_seconds,
                )
                time.sleep(cfg.interval)
                continue

            # Algorithm 2 line 2-7: compute proportional vector N and apply it
            # if it differs from current system configuration.
            if desired != current:
                changed = apply_replica_vector(
                    cfg=cfg,
                    executor=executor,
                    desired=desired,
                    current=current,
                )

                if changed:
                    last_scale_time = now
                    logging.info(
                        "[HAB PROPORTIONAL APPLIED] reason=%s",
                        get_band_reason(cfg, root_latency_ms),
                    )
                else:
                    logging.info("[HAB PROPORTIONAL NOOP] desired vector not applied")

                # Algorithm 2 line 8-12: if R still violates and request rate is
                # stable, do step-by-step exploratory auto-scaling.
                exploratory_changed = run_exploratory_loop_if_needed(
                    cfg=cfg,
                    monitor=monitor,
                    executor=executor,
                    lambda_before_rps=lambda_now_rps,
                    wait_before_first_check_seconds=cfg.post_proportional_wait_seconds,
                )
                if exploratory_changed:
                    last_scale_time = time.time()

            else:
                # Algorithm 2 line 13-14: desired vector already equals current,
                # but R is still outside the band, so exploratory scaling is used.
                logging.info(
                    "[HAB PROPORTIONAL SAME] current already equals N; wait %.1fs then run exploratory scaling",
                    cfg.stabilization_seconds,
                )
                time.sleep(cfg.stabilization_seconds)
                refreshed_lambda_rps = get_entry_rps(monitor, cfg.root_service)
                refreshed_latency_ms = get_root_latency_ms(monitor, cfg.root_service)
                if not is_request_rate_stable(
                    lambda_now_rps,
                    refreshed_lambda_rps,
                    cfg.stable_lambda_rel_delta,
                ):
                    logging.info(
                        "[HAB EXPLORATORY SKIP] request rate changed too much before exploratory: "
                        "lambda_before=%.2f lambda_now=%.2f threshold=%.2f",
                        lambda_now_rps,
                        refreshed_lambda_rps,
                        cfg.stable_lambda_rel_delta,
                    )
                elif not is_latency_outside_band(cfg, refreshed_latency_ms):
                    logging.info(
                        "[HAB EXPLORATORY SKIP] refreshed R=%.2fms now inside band",
                        refreshed_latency_ms,
                    )
                else:
                    changed = exploratory_autoscale_once(
                        cfg=cfg,
                        monitor=monitor,
                        executor=executor,
                        root_latency_ms=refreshed_latency_ms,
                    )
                    if changed:
                        last_scale_time = time.time()

        except Exception as exc:
            logging.exception("[HAB ERROR] %s", exc)

        time.sleep(cfg.interval)


if __name__ == "__main__":
    main()
