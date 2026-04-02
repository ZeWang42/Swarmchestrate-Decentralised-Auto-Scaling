from __future__ import annotations

import csv
import itertools
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from config.exp_config import (
    SERVER_BASE_URL,
    BOOKINFO_HOST,
    NAMESPACE,
    WORKLOAD_NAME,
    HPA_SETTINGS,
    DURATION_SECONDS,
    MONITOR_INTERVAL,
    PROM_URL,
    LOCUST_FILE,
    TMP_DIR,
    WAIT_BETWEEN_EXPERIMENTS_SECONDS,
)


TMP_PATH = Path(TMP_DIR)
TMP_PATH.mkdir(parents=True, exist_ok=True)

SUMMARY_CSV = TMP_PATH / "experiment_summary.csv"
LOCUST_RESULTS_DIR = TMP_PATH / "locust"
LOCUST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Experiment:
    workload_name: str
    hpa_mode: str
    cpu_target: int | None
    min_replicas: int
    max_replicas: int
    

    @property
    def name(self) -> str:
        if self.hpa_mode == "none":
            return f"bookinfo_rps{self.workload_name}_hpa_none"
        return f"bookinfo_rps{self.workload_name}_hpa_cpu{self.cpu_target}"


def get_workload_csv(workload_name: str) -> str:
    print(f"load/book-info/workloads/{workload_name}.csv")
    return f"load/book-info/workloads/{workload_name}.csv"
        #return f"load/book-info/workloads/constant-{workload_name}.csv"


def post_json(url: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    resp = requests.post(url, json=payload, timeout=timeout)

    print("\n--- REQUEST ---")
    print(json.dumps(payload, indent=2, default=str))

    print("\n--- RESPONSE ---")
    print("STATUS:", resp.status_code)

    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)

    resp.raise_for_status()
    return resp.json()



def init_summary_csv() -> None:
    if SUMMARY_CSV.exists():
        return

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "experiment_name",
            "workload_name",
            "workload_csv",
            "hpa_mode",
            "cpu_target",
            "setup_ok",
            "ready_for_load",
            "monitor_log_file",
            "locust_stats_csv",
            "locust_failures_csv",
            "locust_exceptions_csv",
            "locust_stats_history_csv",
            "cleanup_ok",
            "status",
            "error_message",
        ])


def append_summary_row(
    exp: Experiment,
    setup_result: dict[str, Any] | None,
    cleanup_result: dict[str, Any] | None,
    locust_files: dict[str, str] | None,
    status: str,
    error_message: str = "",
) -> None:
    monitor_log_file = ""
    setup_ok = ""
    ready_for_load = ""
    cleanup_ok = ""

    if setup_result:
        setup_ok = str(setup_result.get("ok", ""))
        ready_for_load = str(setup_result.get("ready_for_load", ""))
        monitor_result = setup_result.get("monitor_result") or {}
        monitor_log_file = monitor_result.get("log_file", "")

    if cleanup_result:
        cleanup_ok = str(cleanup_result.get("ok", ""))

    with SUMMARY_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            exp.name,
            exp.workload_name,
            get_workload_csv(exp.workload_name),
            exp.hpa_mode,
            exp.cpu_target if exp.cpu_target is not None else "",
            setup_ok,
            ready_for_load,
            monitor_log_file,
            (locust_files or {}).get("stats_csv", ""),
            (locust_files or {}).get("failures_csv", ""),
            (locust_files or {}).get("exceptions_csv", ""),
            (locust_files or {}).get("stats_history_csv", ""),
            cleanup_ok,
            status,
            error_message,
        ])


def setup_experiment(exp: Experiment) -> dict[str, Any]:
    payload = {
        "app": "bookinfo",
        "namespace": NAMESPACE,
        "workload_name": exp.workload_name,
        "duration_seconds": DURATION_SECONDS,
        "hpa": {
            "mode": exp.hpa_mode,
            "target_cpu_utilization": exp.cpu_target,
            "min_replicas": exp.min_replicas,
            "max_replicas": exp.max_replicas,
        },
        "monitor": {
            "interval": MONITOR_INTERVAL,
            "prom_url": PROM_URL,
            "file_prefix": "mesh_metrics",
        },
    }

    print(f"[SETUP] {exp.name}")
    result = post_json(f"{SERVER_BASE_URL}/experiment/setup", payload)
    print(json.dumps(result, indent=2))
    return result


def cleanup_experiment(exp: Experiment) -> dict[str, Any]:
    payload = {
        "app": "bookinfo",
        "namespace": NAMESPACE,
        "delete_hpa": exp.hpa_mode == "cpu",
        "stop_monitoring": True,
    }

    print(f"[CLEANUP] {exp.name}")
    result = post_json(f"{SERVER_BASE_URL}/experiment/cleanup", payload)
    print(json.dumps(result, indent=2))
    return result


def run_locust(exp: Experiment) -> dict[str, str]:
    prefix = LOCUST_RESULTS_DIR / exp.name
    csv_path = get_workload_csv(exp.workload_name)

    cmd = [
        "locust",
        "-f",
        LOCUST_FILE,
        "--headless",
        "--host",
        BOOKINFO_HOST,
        "--csv",
        str(prefix),
        "--only-summary",
    ]

    env = os.environ.copy()
    env["CSV_PATH"] = csv_path
    env["TIME_MINUTE"] = str(DURATION_SECONDS // 60)
    env["SPAWN_RATE"] = "20"
    env["SCALE_FACTOR"] = "1"



    print("[LOCUST CMD]")
    print(" ".join(cmd))
    print(f"[WORKLOAD] {csv_path}")

    result = subprocess.run(cmd, check=False, env=env)
    print(f"[LOCUST EXIT CODE] {result.returncode}")

    return {
        "exit_code": result.returncode,
        "stats_csv": str(prefix) + "_stats.csv",
        "failures_csv": str(prefix) + "_failures.csv",
        "exceptions_csv": str(prefix) + "_exceptions.csv",
        "stats_history_csv": str(prefix) + "_stats_history.csv",
    }


def build_experiments() -> list[Experiment]:
    experiments: list[Experiment] = []
    for workload_name, hpa in itertools.product(WORKLOAD_NAME, HPA_SETTINGS):
        experiments.append(
            Experiment(
                workload_name=workload_name,
                hpa_mode=hpa["mode"],
                cpu_target=hpa["target_cpu_utilization"],
                min_replicas=hpa["min_replicas"],
                max_replicas=hpa["max_replicas"],
            )
        )
    return experiments


def run_one_experiment(exp: Experiment) -> None:
    setup_result = None
    cleanup_result = None
    locust_files = None

    try:
        setup_result = setup_experiment(exp)
        if not setup_result.get("ready_for_load", False):
            raise RuntimeError("Server is not ready for load")

        locust_files = run_locust(exp)
        cleanup_result = cleanup_experiment(exp)


        status = "success" if locust_files["exit_code"] == 0 else "completed_with_failures"

        append_summary_row(
            exp,
            setup_result,
            cleanup_result,
            locust_files,
            status=status,
            error_message="" if locust_files["exit_code"] == 0 else f"Locust exit code {locust_files['exit_code']}",
        )

    except Exception as exc:
        try:
            cleanup_result = cleanup_experiment(exp)
        except Exception as cleanup_exc:
            cleanup_result = {"ok": False, "error": str(cleanup_exc)}

        append_summary_row(
            exp,
            setup_result,
            cleanup_result,
            locust_files,
            status="failed",
            error_message=str(exc),
        )
        print(f"[ERROR] {exp.name}: {exc}")


def main() -> None:
    init_summary_csv()
    experiments = build_experiments()

    print("[PLAN]")
    for exp in experiments:
        print(" -", exp.name)

    for i, exp in enumerate(experiments, start=1):
        print(f"\n=== Experiment {i}/{len(experiments)}: {exp.name} ===")
        run_one_experiment(exp)

        if i < len(experiments):
            print(f"[WAIT] {WAIT_BETWEEN_EXPERIMENTS_SECONDS}s")
            time.sleep(WAIT_BETWEEN_EXPERIMENTS_SECONDS)

    print(f"\nSummary written to {SUMMARY_CSV}")


if __name__ == "__main__":
    main()
