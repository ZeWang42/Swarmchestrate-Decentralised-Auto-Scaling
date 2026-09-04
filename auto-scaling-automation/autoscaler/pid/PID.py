from __future__ import annotations

import logging
import math
import os
import time

from kubernetes import config

from execution import Executor
from monitoring import Monitor
from queue_das_logging import build_deployment_monitoring_log

# =============================================================================
# APP CONFIGURATION & CONSTANTS
# =============================================================================

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

BASELINE_SLO_TIME_MS_BY_APP: dict[str, dict[str, float | None]] = {
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

BASELINE_PROCESSING_TIME_MS: dict[str, float | None] = {
    service: value
    for app_table in BASELINE_PROCESSING_TIME_MS_BY_APP.values()
    for service, value in app_table.items()
}

SELECTED_APP_BASELINE_PROCESSING_TIME_MS: dict[str, float | None] = (
    BASELINE_PROCESSING_TIME_MS_BY_APP.get(APP_NAME, {})
)

LOG_FILE = os.getenv("LOG_FILE", "/tmp/pid-autoscaler.log")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)

# =============================================================================
# PID CONTROLLER CONFIGURATION
# =============================================================================

# Set default env configuration for PID tuning
PID_KP = float(os.getenv("PID_KP", "0.01"))      # Proportional gain
PID_KI = float(os.getenv("PID_KI", "0.001"))     # Integral gain
PID_KD = float(os.getenv("PID_KD", "0.005"))     # Derivative gain
INTEGRAL_MAX = float(os.getenv("PID_INTEGRAL_MAX", "10.0")) # Anti-windup clamp
DERIVATIVE_ALPHA = float(os.getenv("PID_D_ALPHA", "0.7"))    # Smoothing factor for D-term

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def valid_number(x: float) -> bool:
    """Check if a number is valid (not None, finite, non-negative)."""
    return x is not None and math.isfinite(x) and x >= 0


def percentile(values: list[float], q: float) -> float | None:
    """Compute the q-th percentile of a list of values."""
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


LATENCY_SLO_MODE_FIXED = "fixed"
LATENCY_SLO_MODE_ONLINE_LEARNING = "online_learning"


def normalize_latency_slo_mode(raw_mode: str) -> str:
    """Map LATENCY_SLO_MODE env values to one of the two supported modes."""
    mode = (raw_mode or "").strip().lower()
    if mode in ("online_learning", "online-learning", "adaptive", "learning"):
        return LATENCY_SLO_MODE_ONLINE_LEARNING
    return LATENCY_SLO_MODE_FIXED


def get_configured_latency_slo_ms(app_name: str, deployment: str) -> float:
    """Get configured latency SLO from environment or baseline config table."""
    env_names = (
        "LATENCY_SLO_MS",
        "SLO_MS",
        "SLO_LATENCY_MS",
        "FRONTEND_HEALTHY_LATENCY_MS",
    )
    for env_name in env_names:
        raw_value = os.getenv(env_name)
        if raw_value is not None and raw_value.strip():
            try:
                value = float(raw_value)
                if value > 0:
                    return value
            except ValueError:
                logging.warning("Ignoring invalid %s=%r for %s/%s", env_name, raw_value, app_name, deployment)

    latency_slo_ms = BASELINE_SLO_TIME_MS_BY_APP.get(app_name, {}).get(deployment)
    if latency_slo_ms is None:
        latency_slo_ms = BASELINE_SLO_TIME_MS_BY_APP.get(app_name, {}).get("default")
    return float(latency_slo_ms) if latency_slo_ms is not None else 500.0


def update_healthy_latency_history(
    history_ms: list[float],
    observed_latency_ms: float,
    target_latency_ms: float,
    max_samples: int = 40,
) -> bool:
    """
    Track healthy latency samples for adaptive SLO learning.
    Returns True if the sample was added, False otherwise.
    """
    if not valid_number(observed_latency_ms) or observed_latency_ms <= 0:
        return False
    if not valid_number(target_latency_ms) or target_latency_ms <= 0:
        return False
    history_ms.append(float(observed_latency_ms))
    if len(history_ms) > max_samples:
        del history_ms[: len(history_ms) - max_samples]
    return True


def healthy_percentile_target_ms(history_ms: list[float]) -> float | None:
    """
    Compute adaptive SLO target as the median (50th percentile) of healthy latency history.
    """
    return percentile(history_ms, 0.50)


def wait_for_next_loop(timeout_s: float) -> None:
    """Sleep for the specified timeout in a non-blocking way that respects signals."""
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        time.sleep(min(0.5, deadline - time.time()))


def pid_control_step(
    error: float,
    dt: float,
    integral: float,
    prev_error: float,
    prev_filtered_d: float,
    kp: float = PID_KP,
    ki: float = PID_KI,
    kd: float = PID_KD,
) -> tuple[float, float, float, float]:
    """
    Calculates the PID control output (delta replicas).
    Returns: (control_output, updated_integral, current_raw_d, updated_filtered_d)
    """
    if dt <= 0:
        return 0.0, integral, 0.0, prev_filtered_d

    # 1. Proportional Term
    p_term = kp * error

    # 2. Integral Term (with Anti-Windup Clamping)
    updated_integral = integral + (error * dt)
    updated_integral = max(-INTEGRAL_MAX, min(INTEGRAL_MAX, updated_integral))
    i_term = ki * updated_integral

    # 3. Derivative Term (with EWMA Low-Pass Filter)
    raw_d = (error - prev_error) / dt
    filtered_d = (DERIVATIVE_ALPHA * prev_filtered_d) + ((1.0 - DERIVATIVE_ALPHA) * raw_d)
    d_term = kd * filtered_d

    # Total Continuous Control Output
    u_t = p_term + i_term + d_term
    return u_t, updated_integral, raw_d, filtered_d


def das_loop_pid(
    monitor: Monitor,
    executor: Executor,
    deployment: str,
    interval: float,
    scale_up_cooldown: float,
    scale_down_cooldown: float,
    min_replicas: int,
    max_replicas: int,
) -> None:
    """
    Decentralized PID-based Autoscaling Loop for a single microservice deployment.
    """
    last_scale_time = 0.0
    last_loop_time = time.time()

    # PID State Registers
    integral_err = 0.0
    prev_error = 0.0
    prev_filtered_d = 0.0

    # Local Adaptive Target State
    healthy_self_percentile_history_ms: list[float] = []

    is_root = deployment in ROOT_SERVICES
    startup_mode = (
        LATENCY_SLO_MODE_FIXED
        if is_root
        else normalize_latency_slo_mode(os.getenv("LATENCY_SLO_MODE", LATENCY_SLO_MODE_ONLINE_LEARNING))
    )

    logging.info(
        "Starting Decentralized PID Controller for '%s' [Kp=%.4f, Ki=%.4f, Kd=%.4f] | Latency SLO Mode: %s",
        deployment, PID_KP, PID_KI, PID_KD, startup_mode
    )

    while True:
        try:
            now = time.time()
            dt = now - last_loop_time
            last_loop_time = now

            # Fetch cluster state
            deployment_resources = monitor.get_deployment_resources(deployment)
            current_pods = deployment_resources.running_pods

            # Recovery logic for zero pods
            if current_pods <= 0:
                logging.warning("[%s] Zero running pods detected! Triggering emergency scale-up.", deployment)
                executor.scale_by(deployment, delta=1, min_replicas=min_replicas, max_replicas=max_replicas)
                integral_err = 0.0  # Reset integral state
                wait_for_next_loop(interval)
                continue

            # Telemetry Fetch
            http_rpm = monitor.get_http_rpm_as_dst(deployment) or 0.0
            http_p95 = monitor.get_http_latency_p95_as_dst(deployment) or 0.0
            grpc_p95 = monitor.get_grpc_latency_p95_as_dst(deployment) or 0.0
            
            # Target percentile latency calculation (R_observed)
            R_observed_ms = max(http_p95, grpc_p95)

            # Determine Target SLO (R_target)
            APP_NAME = os.getenv("APP_NAME", "onlineboutique").strip().lower()
            configured_slo_ms = get_configured_latency_slo_ms(APP_NAME, deployment)

            is_root = deployment in ROOT_SERVICES
            effective_mode = (
                LATENCY_SLO_MODE_FIXED
                if is_root
                else normalize_latency_slo_mode(os.getenv("LATENCY_SLO_MODE", LATENCY_SLO_MODE_ONLINE_LEARNING))
            )

            if effective_mode == LATENCY_SLO_MODE_ONLINE_LEARNING:
                # Non-root SLO target starts at the configured/root-derived baseline, then
                # online-learns its own healthy latency percentile whenever the root
                # service is currently within its own SLO (i.e. the system is healthy).
                root_slo_ms = get_configured_latency_slo_ms(APP_NAME, ROOT_SERVICE)
                root_latency_ms = monitor.get_http_latency_p95_as_dst(ROOT_SERVICE)
                root_is_healthy = valid_number(root_latency_ms) and root_latency_ms < root_slo_ms
                if root_is_healthy:
                    update_healthy_latency_history(
                        healthy_self_percentile_history_ms,
                        R_observed_ms,
                        configured_slo_ms
                    )
                learned_target = healthy_percentile_target_ms(healthy_self_percentile_history_ms)
                R_target_ms = learned_target if learned_target is not None else configured_slo_ms
            else:
                R_target_ms = configured_slo_ms

            # Compute PID Error: e(t) = R_observed - R_target
            # Positive Error -> Latency is higher than SLO target -> Needs MORE pods
            # Negative Error -> Latency is lower than SLO target -> Candidate for scale-down
            error_ms = R_observed_ms - R_target_ms

            # Execute Control Calculation
            u_t, integral_err, raw_d, prev_filtered_d = pid_control_step(
                error=error_ms,
                dt=dt,
                integral=integral_err,
                prev_error=prev_error,
                prev_filtered_d=prev_filtered_d,
            )
            prev_error = error_ms

            # Quantize continuous PID signal to discrete replica counts
            # Positive u_t suggests adding pods; Negative u_t suggests removing pods
            if not math.isfinite(u_t):
                logging.warning("[%s PID] Non-finite control output u(t)=%s, skipping this cycle.", deployment, u_t)
                wait_for_next_loop(interval)
                continue
            recommended_delta = math.floor(u_t) if u_t < 0 else math.ceil(u_t)
            
            # Ignore minor fractional noise around zero
            if abs(u_t) < 0.5:
                recommended_delta = 0

            target_replicas = max(min_replicas, min(max_replicas, current_pods + recommended_delta))
            actual_delta = target_replicas - current_pods

            logging.info(
                "[%s PID] Latency: %.2fms | Target: %.2fms | Error: %.2fms | u(t): %.3f | P_pods: %d -> %d",
                deployment, R_observed_ms, R_target_ms, error_ms, u_t, current_pods, target_replicas
            )

            # Execution with Cooldown Guards
            in_scale_up_cooldown = (now - last_scale_time) < scale_up_cooldown
            in_scale_down_cooldown = (now - last_scale_time) < scale_down_cooldown

            if actual_delta > 0 and not in_scale_up_cooldown:
                res = executor.scale_by(deployment, delta=actual_delta, min_replicas=min_replicas, max_replicas=max_replicas)
                logging.info("[%s PID] SCALE UP (+%d) Result: %s", deployment, actual_delta, res)
                last_scale_time = now
                integral_err = 0.0  # Reset integral accumulation after scaling action

            elif actual_delta < 0 and not in_scale_down_cooldown:
                res = executor.scale_by(deployment, delta=actual_delta, min_replicas=min_replicas, max_replicas=max_replicas)
                logging.info("[%s PID] SCALE DOWN (%d) Result: %s", deployment, actual_delta, res)
                last_scale_time = now
                integral_err = 0.0  # Reset integral accumulation after scaling action

        except Exception as err:
            logging.error("[%s PID] Exception in control loop: %s", deployment, err, exc_info=True)

        wait_for_next_loop(interval)


def main() -> None:
    """
    Main entry point for PID-based decentralized autoscaler.
    Loads configuration from environment variables and Kubernetes cluster.
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    # Load configuration from environment variables
    interval = float(os.getenv("INTERVAL", "15"))
    scale_up_cooldown = float(os.getenv("SCALE_UP_COOLDOWN_SECONDS", "30"))
    scale_down_cooldown = float(os.getenv("SCALE_DOWN_COOLDOWN_SECONDS", "120"))
    namespace = os.getenv("NAMESPACE", "default")
    deployment = os.getenv("TARGET_DEPLOYMENT", "productpage-v1")
    prom_url = os.getenv("PROM_URL", "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query")
    min_replicas = int(os.getenv("MIN_REPLICAS", "1"))
    max_replicas = int(os.getenv("MAX_REPLICAS", "10"))

    # Create monitoring and execution instances
    monitor = Monitor(namespace=namespace, prom_url=prom_url)
    executor = Executor(namespace=namespace)

    logging.info(
        "PID Autoscaler Initialized - Deployment: %s | Interval: %.1fs | Min: %d, Max: %d",
        deployment, interval, min_replicas, max_replicas
    )

    # Start the decentralized PID-based autoscaling loop
    das_loop_pid(
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