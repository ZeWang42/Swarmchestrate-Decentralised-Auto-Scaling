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


ROOT_SERVICES = {"frontend"}
EXTERNAL_UPSTREAMS = {"gateway", "istio-ingressgateway", "unknown", ""}


LOG_FILE = os.getenv("LOG_FILE", "/tmp/customdas.log")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),              # kubectl logs
        logging.FileHandler(LOG_FILE),        # file inside container
    ],
)


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


def top_p95_bottlenecks(
    deployment: str,
    node_type: str,
    downstream_p95: dict[str, float],
) -> list[tuple[str, float | str]]:
    if node_type == "leaf":
        return [(deployment, "self")]

    ranked = sorted(
        downstream_p95.items(),
        key=lambda item: item[1] or 0.0,
        reverse=True,
    )

    return ranked[:3]


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


def recommend_replicas_slo(
    lambda_rps: float,
    mu: float,
    wq_allowed_s: float,
    min_replicas: int,
    max_replicas: int,
    current_replicas: int,
) -> int:
    """Find minimum c such that modeled Wq satisfies SLO."""
    if not all(valid_number(x) for x in [lambda_rps, mu, wq_allowed_s]):
        print(f"Invalid input for recommend_replicas_slo: lambda_rps={lambda_rps}, mu={mu}, wq_allowed_s={wq_allowed_s}", flush=True)
        return current_replicas

    if lambda_rps <= 0 or mu <= 0 or wq_allowed_s < 0:
        print(f"Non-positive input for recommend_replicas_slo: lambda_rps={lambda_rps}, mu={mu}, wq_allowed_s={wq_allowed_s}", flush=True)
        return current_replicas

    for c in range(min_replicas, max_replicas + 1):
        wq_model_s = expected_queueing_delay(lambda_rps, mu, c)

        if math.isfinite(wq_model_s) and wq_model_s <= wq_allowed_s:
            return c
    return max_replicas


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

    logging.info(
        "Starting DAS for deployment '%s' [Interval: %.1fs | Up Cooldown: %.1fs, Down Cooldown: %.1fs]",
        deployment, interval, scale_up_cooldown, scale_down_cooldown
    )
    
    interval = 30  # override for testing
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
                time.sleep(interval)
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

            http_latency_p50_as_dst = monitor.get_http_latency_p50_as_dst(deployment)
            grpc_latency_p50_as_dst = monitor.get_grpc_latency_p50_as_dst(deployment)
            http_latency_avg_as_dst = monitor.get_http_latency_as_dst(deployment)
            grpc_latency_avg_as_dst = monitor.get_grpc_latency_as_dst(deployment)
            http_latency_p95_as_dst = monitor.get_http_latency_p95_as_dst(deployment)
            grpc_latency_p95_as_dst = monitor.get_grpc_latency_p95_as_dst(deployment)

            http_rpm_as_src = monitor.get_http_rpm_as_src(deployment)
            grpc_rpm_as_src = monitor.get_grpc_rpm_as_src(deployment)

            http_latency_p50_as_src = monitor.get_http_latency_p50_as_src(deployment)
            grpc_latency_p50_as_src = monitor.get_grpc_latency_p50_as_src(deployment)
            http_latency_avg_as_src = monitor.get_http_latency_as_src(deployment)
            grpc_latency_avg_as_src = monitor.get_grpc_latency_as_src(deployment)
            http_latency_p95_as_src = monitor.get_http_latency_p95_as_src(deployment)
            grpc_latency_p95_as_src = monitor.get_grpc_latency_p95_as_src(deployment)

            http_rpm_mesh_as_dst = monitor.get_http_rpm_mesh_as_dst(deployment)
            grpc_rpm_mesh_as_dst = monitor.get_grpc_rpm_mesh_as_dst(deployment)

            http_latency_mesh_avg_as_dst = monitor.get_http_latency_mesh_as_dst(deployment)
            grpc_latency_mesh_avg_as_dst = monitor.get_grpc_latency_mesh_as_dst(deployment)

            http_latency_p95_mesh_as_dst = monitor.get_http_latency_p95_mesh_as_dst(deployment)
            grpc_latency_p95_mesh_as_dst = monitor.get_grpc_latency_p95_mesh_as_dst(deployment)

            http_rpm_mesh_as_src = monitor.get_http_rpm_mesh_as_src(deployment)
            grpc_rpm_mesh_as_src = monitor.get_grpc_rpm_mesh_as_src(deployment)

            http_latency_mesh_avg_as_src = monitor.get_http_latency_mesh_as_src(deployment)
            grpc_latency_mesh_avg_as_src = monitor.get_grpc_latency_mesh_as_src(deployment)

            http_latency_p95_mesh_as_src = monitor.get_http_latency_p95_mesh_as_src(deployment)
            grpc_latency_p95_mesh_as_src = monitor.get_grpc_latency_p95_mesh_as_src(deployment)

            upstreams = monitor.get_upstreams(deployment)
            downstreams = monitor.get_downstreams(deployment)

            node_type = classify_node(deployment, upstreams, downstreams)

            logging.info("Deployment '%s' node type is: %s", deployment, node_type)

            if not p2p_agent.ready:
                logging.info("P2P not ready yet for %s; skip sending messages", deployment)
            else:
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
                "http_latency_p95_as_dst": http_latency_p95_as_dst,
                "http_latency_avg_as_dst": http_latency_avg_as_dst,
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
                time.sleep(interval)
                continue

            #############
            # Step 2: Queueing Model & Local Execution-Only Service Time ($S_{\text{local}}$)
            #############
            lambda_rps = (http_rpm_as_dst + grpc_rpm_as_dst) / 60.0

            R_p50_ms = http_latency_p50_as_dst + grpc_latency_p50_as_dst
            R_p95_ms = http_latency_p95_as_dst + grpc_latency_p95_as_dst
            R_avg_ms = http_latency_avg_as_dst + grpc_latency_avg_as_dst

            R_p50_s = R_p50_ms / 1000.0
            R_avg_s = R_avg_ms / 1000.0
            R_p95_s = R_p95_ms / 1000.0

            # Establish the base service time fallback baseline
            S_local_s = R_p50_s

            # Execution-Only Service Time Calculation ($S_{\text{local}}$) for Root/Intermediate Nodes
            if node_type in ("root", "intermediate") and lambda_rps > 0:
                S_local_s = R_avg_s
                downstream_wait_sum_s = 0.0
                logging.info("\n[[DEBUG] Decomposing Local Service Time S from Overall Transit Time R]]")
                http_rpm_mesh_src = http_rpm_mesh_as_src or {}
                grpc_rpm_mesh_src = grpc_rpm_mesh_as_src or {}
                http_avg_mesh_src = http_latency_mesh_avg_as_src or {}
                grpc_avg_mesh_src = grpc_latency_mesh_avg_as_src or {}

                for d in downstreams:
                    if d in EXTERNAL_UPSTREAMS:
                        continue
                    
                    # Compute total downstream arrival rate generated by this deployment
                    d_rpm = (http_rpm_mesh_src.get(d, 0.0) or 0.0) + (grpc_rpm_mesh_src.get(d, 0.0) or 0.0)
                    d_rps = d_rpm / 60.0
                    
                    # Retrieve the real-time average processing transit cost of that downstream
                    d_avg_ms = (http_avg_mesh_src.get(d, 0.0) or 0.0) + (grpc_avg_mesh_src.get(d, 0.0) or 0.0)
                    d_avg_s = d_avg_ms / 1000.0
                    
                    # Weight downstream time by call intensity per inbound request
                    requests_per_task = d_rps / lambda_rps
                    downstream_wait_sum_s += (requests_per_task * d_avg_s)
                logging.info(f"[DEBUG] Estimated downstream waiting time contribution to overall transit time: {downstream_wait_sum_s:.2f} s")
                # Isolate local runtime overhead from sub-call latency blockers
                S_local_s = max(0.001, S_local_s - downstream_wait_sum_s)
                logging.info("[LEAN SERVICE TIME] Overall Transit P50: %.2fms | Isolated Local Engine ($S_{\\text{local}}$): %.2fms", 
                             R_p50_s * 1000, S_local_s * 1000)

            # Local structural state/thread lock contention handling
            if R_avg_s > (3.0 * R_p50_s):
                logging.info("[CONTENTION ALERT] Average latency structurally higher than P50.")
                S_s = (S_local_s + R_avg_s) / 2.0
            else:
                S_s = S_local_s

            mu = 1.0 / S_s if S_s > 0 else 0.0
            Wq_s = max(0.0, R_p95_s - R_p50_s)
            Q = lambda_rps * Wq_s
            rho = (lambda_rps / (pods_count * mu) if mu > 0 and pods_count > 0 else 0.0)

            #############
            # Step 3: Analysis & Replicas Recommendation
            #############
            rho_target = float(os.getenv("RHO_TARGET", "0.8"))

            recommended_replicas = (math.ceil(lambda_rps / (mu * rho_target)) if mu > 0 else pods_count)
            recommended_replicas = max(min_replicas, min(max_replicas, recommended_replicas))

            hpa_recommended = math.ceil(pods_count * ((cpu_utilisation / 100.0) / 0.8))
            hpa_recommended = max(min_replicas, min(max_replicas, hpa_recommended))

            latency_slo_ms = float(os.getenv("LATENCY_SLO_MS", "500"))
            if node_type == "leaf":
                latency_slo_ms = float(os.getenv("LATENCY_SLO_MS_LEAF_MS", "10"))
            wq_allowed_s = max(0.01, (latency_slo_ms / 1000.0) - S_s)

            p_wait_current = erlang_c(lambda_rps, mu, pods_count)
            wq_model_current_s = expected_queueing_delay(lambda_rps, mu, pods_count)

            slo_recommended = recommend_replicas_slo(
                lambda_rps=lambda_rps,
                mu=mu,
                wq_allowed_s=wq_allowed_s,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                current_replicas=pods_count,
            )

            p_wait_display = f"{p_wait_current:.4f}" if math.isfinite(p_wait_current) else "nan"
            wq_model_display_ms = (
                wq_model_current_s * 1000 if math.isfinite(wq_model_current_s)
                else float("inf") if wq_model_current_s == float("inf") else float("nan")
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
                f"  P50 (baseline transit)  : {R_p50_ms:.2f} ms\n"
                f"  Avg (observed transit)  : {R_avg_ms:.2f} ms\n"
                f"  P95 (tail transit)      : {R_p95_ms:.2f} ms\n"
                "\n"
                "[Decomposition Modeling]\n"
                f"  Isolated Service time S : {S_s * 1000:.2f} ms\n"
                f"  Waiting time Wq         : {Wq_s * 1000:.2f} ms\n"
                f"  Queue ratio (Wq/R)      : {(Wq_s / R_p95_s if R_p95_s > 0 else 0):.2f}\n"
                "\n"
                "[Resource Boundaries]\n"
                f"  ρ (local utilisation)   : {rho:.2f}\n"
                f"  Status                  : "
                f"{'OVERLOADED 🔴' if rho >= 1 else 'HIGH 🟠' if rho > 0.8 else 'OK 🟢'}\n"
                "\n"
                "[Replica Calculation Results]\n"
                f"  Method 1: Queueing Recom: {recommended_replicas} (delta: {recommended_replicas - pods_count:+d})\n"
                f"  Method 2: HPA CPU Recom : {hpa_recommended} (delta: {hpa_recommended - pods_count:+d})\n"
                f"  Method 3: SLO Target Set: {slo_recommended} (delta: {slo_recommended - pods_count:+d})\n"
                "===================================================\n"
            )

            logging.info(
                build_deployment_monitoring_log(
                    deployment=deployment, cpu_m=cpu_m, mem_mib=mem_mib, pods_count=pods_count,
                    cpu_utilisation=cpu_utilisation, mem_utilisation=mem_utilisation,
                    http_rpm_as_dst=http_rpm_as_dst, grpc_rpm_as_dst=grpc_rpm_as_dst,
                    http_latency_p50_as_dst=http_latency_p50_as_dst, grpc_latency_p50_as_dst=grpc_latency_p50_as_dst,
                    http_latency_avg_as_dst=http_latency_avg_as_dst, grpc_latency_avg_as_dst=grpc_latency_avg_as_dst,
                    http_latency_p95_as_dst=http_latency_p95_as_dst, grpc_latency_p95_as_dst=grpc_latency_p95_as_dst,
                    http_rpm_as_src=http_rpm_as_src, grpc_rpm_as_src=grpc_rpm_as_src,
                    http_latency_p50_as_src=http_latency_p50_as_src, grpc_latency_p50_as_src=grpc_latency_p50_as_src,
                    http_latency_avg_as_src=http_latency_avg_as_src, grpc_latency_avg_as_src=grpc_latency_avg_as_src,
                    http_latency_p95_as_src=http_latency_p95_as_src, grpc_latency_p95_as_src=grpc_latency_p95_as_src,
                    http_rpm_mesh_as_dst=http_rpm_mesh_as_dst, grpc_rpm_mesh_as_dst=grpc_rpm_mesh_as_dst,
                    http_latency_mesh_avg_as_dst=http_latency_mesh_avg_as_dst, grpc_latency_mesh_avg_as_dst=grpc_latency_mesh_avg_as_dst,
                    http_latency_p95_mesh_as_dst=http_latency_p95_mesh_as_dst, grpc_latency_p95_mesh_as_dst=grpc_latency_p95_mesh_as_dst,
                    http_rpm_mesh_as_src=http_rpm_mesh_as_src, grpc_rpm_mesh_as_src=grpc_rpm_mesh_as_src,
                    http_latency_mesh_avg_as_src=http_latency_mesh_avg_as_src, grpc_latency_mesh_avg_as_src=grpc_latency_mesh_avg_as_src,
                    http_latency_p95_mesh_as_src=http_latency_p95_mesh_as_src, grpc_latency_p95_mesh_as_src=grpc_latency_p95_mesh_as_src,
                    upstreams=upstreams, downstreams=downstreams,
                )
            )

            #############
            # Step 3.5: Reactive P2P Backpressure Signaling Engine
            #############
            p95_mesh_src = merge_dict_metric(http_latency_p95_mesh_as_src, grpc_latency_p95_mesh_as_src)
            bottlenecks = top_p95_bottlenecks(deployment=deployment, node_type=node_type, downstream_p95=p95_mesh_src)

            logging.info("\n[[DEBUG] Testing Potential Bottlenecks]")
            if node_type == "leaf":
                logging.info(f"1. {deployment}: self")
            elif bottlenecks:
                for i, (service, p95) in enumerate(bottlenecks, start=1):
                    logging.info(f"{i}. {service}: p95={float(p95):.2f} ms")
            else:
                logging.info("None detected")

            for bottleneck in bottlenecks:
                if bottleneck[0] in ("", None, "unknown") or bottleneck[0] == p2p_agent.peer_id:
                    continue
                
                logging.info(f"[[DEBUG] Triggering backpressure message to downstream bottleneck: {bottleneck[0]}]")
                p2p_agent.send_message(
                    bottleneck[0],
                    "MSG_HELLO",
                    {
                        "from": p2p_agent.peer_id,
                        "msg": "[BACKPRESSURE WARNING] Degradation detected along your downstream execution branch.",
                        "timestamp": time.time(),
                    },
                )

            #############
            # Step 4: Directional Execution Cooldown Routing
            #############
            delta_replicas = slo_recommended - pods_count

            if delta_replicas > 0:
                if now - last_scale_up_time < scale_up_cooldown:
                    logging.info("[COOLDOWN HOLD] Scale-Up request throttled. Elapsed: %.1fs | Required Target: %.1fs", 
                                 now - last_scale_up_time, scale_up_cooldown)
                    time.sleep(interval)
                    continue

                result = executor.scale_by(deployment, delta=delta_replicas, min_replicas=min_replicas, max_replicas=max_replicas)
                last_scale_up_time = now
                logging.info("[SCALE UP ACTION] %s scaling delta=%d executed. Result=%s", deployment, delta_replicas, result)

            elif delta_replicas < 0:
                if now - last_scale_down_time < scale_down_cooldown:
                    logging.info("[COOLDOWN HOLD] Scale-Down request throttled. Elapsed: %.1fs | Required Target: %.1fs", 
                                 now - last_scale_down_time, scale_down_cooldown)
                    time.sleep(interval)
                    continue

                result = executor.scale_by(deployment, delta=delta_replicas, min_replicas=min_replicas, max_replicas=max_replicas)
                last_scale_down_time = now
                logging.info("[SCALE DOWN ACTION] %s scaling delta=%d executed. Result=%s", deployment, delta_replicas, result)
                
            else:
                logging.info("[HOLD] %s system configuration matches current optimal SLO replica requirements.", deployment)

        except Exception as exc:
            logging.exception("[ERROR] %s", exc)

        time.sleep(interval)


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