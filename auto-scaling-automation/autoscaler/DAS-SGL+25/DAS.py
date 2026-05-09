from __future__ import annotations

import logging
import math
import os
import random
import time

from random import uniform
from kubernetes import config

from monitoring import Monitor
from execution import Executor

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def prob_scale_down(rho: float, alpha: float, tau_min: float, c: float, s: float) -> float:
    """
    DOWN-region probability:
        min(c, exp((s / (tau_min - rho)) * (alpha - rho)))
    valid only for rho < tau_min
    """
    eps = 1e-9
    if rho >= tau_min:
        return 0.0

    denom = max(tau_min - rho, eps)
    exponent = s * (alpha - rho) / denom
    exponent = max(min(exponent, 50), -50)
    return min(c, math.exp(exponent))


def prob_scale_up(rho: float, beta: float, tau_max: float, c: float, s: float) -> float:
    """
    UP-region probability:
        min(c, exp((s / (rho - tau_max)) * (rho - beta)))
    valid only for rho > tau_max
    """
    eps = 1e-9
    if rho <= tau_max:
        return 0.0

    denom = max(rho - tau_max, eps)
    exponent = s * (rho - beta) / denom
    exponent = max(min(exponent, 50), -50)
    return min(c, math.exp(exponent))


def main() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    # Load envs 
    alpha = float(os.getenv("ALPHA_DOWN_THRESHOLD", "30"))
    tau_min = float(os.getenv("TAU_MIN", "60"))
    tau_max = float(os.getenv("TAU_MAX", "80"))
    beta = float(os.getenv("BETA_UP_THRESHOLD", "90"))
    c = float(os.getenv("C_MAX_PROBABILITY", "1.0"))
    s = float(os.getenv("S_STEEPNESS", "3.0"))
    interval = float(os.getenv("INTERVAL", "15"))
    cooldown_seconds = float(os.getenv("COOLDOWN_SECONDS", "30"))
    namespace = os.getenv("NAMESPACE", "default")
    deployment = os.getenv("TARGET_DEPLOYMENT", "productpage-v1")
    prom_url = os.getenv(
        "PROM_URL",
        "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    )
    min_replicas = int(os.getenv("MIN_REPLICAS", "1"))
    max_replicas = int(os.getenv("MAX_REPLICAS", "10"))


    # Initialise monitor and executor
    monitor = Monitor(namespace=namespace, prom_url=prom_url)
    executor = Executor(namespace=namespace)

    last_scale_time = 0.0

    logging.info(
        "Starting DAS for deployment '%s' with interval %.1fs",
        deployment,
        interval,
    )

    while True:
        try:
            now = time.time()
            
            if now - last_scale_time < cooldown_seconds:
                logging.info("[COOLDOWN]")
                time.sleep(interval)
                continue

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
                last_scale_time = now
                time.sleep(interval)
                continue

            pods = monitor.list_deployment_pods(deployment)

            delta_replicas = 0
            active_pods = 0

            # the main loop: iterative over all pods of the deployment
            # decide on the total number of pods using the accumulated delta value
            for pod in pods:
                pod_name = pod.metadata.name
                phase = pod.status.phase or "Unknown"

                if phase != "Running":
                    logging.warning("Skipping pod '%s' in phase '%s'", pod_name, phase)
                    continue

                active_pods += 1

                resources = monitor.get_pod_resources(pod_name)
                utilisation = monitor.get_pod_utilisation(deployment, pod_name)
                rho = utilisation.cpu_pct

                logging.info(
                    "pod=%s cpu_used=%sm mem_used=%sMiB cpu_pct=%.2f mem_pct=%.2f",
                    pod_name,
                    resources.cpu_m,
                    resources.mem_mib,
                    utilisation.cpu_pct,
                    utilisation.mem_pct,
                )

                # DAS probabilistic decision
                if rho < tau_min:
                    p_down = prob_scale_down(rho, alpha, tau_min, c, s)
                    draw = random.random()

                    logging.info(
                        "pod=%s region=DOWN rho=%.2f p_down=%.4f draw=%.4f",
                        pod_name,
                        rho,
                        p_down,
                        draw,
                    )

                    if draw < p_down:
                        delta_replicas -= 1

                elif rho > tau_max:
                    p_up = prob_scale_up(rho, beta, tau_max, c, s)
                    draw = random.random()

                    logging.info(
                        "pod=%s region=UP rho=%.2f p_up=%.4f draw=%.4f",
                        pod_name,
                        rho,
                        p_up,
                        draw,
                    )

                    if draw < p_up:
                        delta_replicas += 1

                else:
                    logging.info(
                        "pod=%s region=HOLD rho=%.2f within [%.2f, %.2f]",
                        pod_name,
                        rho,
                        tau_min,
                        tau_max,
                    )

            if active_pods == 0:
                logging.warning("No active running pods found for deployment '%s'", deployment)
                time.sleep(interval)
                continue

            if delta_replicas != 0:
                result = executor.scale_by(
                    deployment,
                    delta=delta_replicas,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                )
                last_scale_time = now
                # TODO: cooldown time in range 30-90
                cooldown_seconds = uniform(30, 90)

                if delta_replicas > 0:
                    logging.info(
                        "[SCALE UP] %s delta_replicas=%d result=%s",
                        deployment,
                        delta_replicas,
                        result,
                    )
                else:
                    logging.info(
                        "[SCALE DOWN] %s delta_replicas=%d result=%s",
                        deployment,
                        delta_replicas,
                        result,
                    )
            else:
                logging.info(
                    "[HOLD] %s no scaling action triggered",
                    deployment,
                )

        except Exception as exc:
            logging.exception("[ERROR] %s", exc)

        time.sleep(interval)


if __name__ == "__main__":
    main()
