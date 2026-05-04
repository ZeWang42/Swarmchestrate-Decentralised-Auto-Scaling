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
    NAMESPACE,
    WORKLOAD_NAME,
    AUTOSCALER_SETTINGS,
    DURATION_SECONDS,
    MONITOR_INTERVAL,
    PROM_URL,
    TMP_DIR,
    WAIT_BETWEEN_EXPERIMENTS_SECONDS,
)

try:
    from config.exp_config import APP_NAME
except ImportError:
    APP_NAME = "bookinfo"

try:
    from config.exp_config import BOOKINFO_HOST
except ImportError:
    BOOKINFO_HOST = ""

try:
    from config.exp_config import ONLINE_BOUTIQUE_HOST
except ImportError:
    ONLINE_BOUTIQUE_HOST = ""

try:
    from config.exp_config import LOCUST_FILES
except ImportError:
    LOCUST_FILES = {}

try:
    from config.exp_config import LOCUST_FILE
except ImportError:
    LOCUST_FILE = ""


APP_CONFIG = {
    "bookinfo": {
        "host": BOOKINFO_HOST,
        "workload_dir": "load/book-info/workloads",
        "locust_file": LOCUST_FILES.get("bookinfo") or LOCUST_FILE or "load/book-info/wiki_locustfile.py",
        "name_prefix": "bookinfo",
    },
    "onlineboutique": {
        "host": ONLINE_BOUTIQUE_HOST,
        "workload_dir": "load/online-boutique/workloads",
        "locust_file": LOCUST_FILES.get("onlineboutique") or LOCUST_FILE or "load/online-boutique/wiki_locustfile.py",
        "name_prefix": "onlineboutique",
    },
}

if APP_NAME not in APP_CONFIG:
    raise ValueError(f"Unsupported APP_NAME={APP_NAME!r}. Use 'bookinfo' or 'onlineboutique'.")

CURRENT_APP = APP_CONFIG[APP_NAME]

TMP_PATH = Path(TMP_DIR)
TMP_PATH.mkdir(parents=True, exist_ok=True)

SUMMARY_CSV = TMP_PATH / f"{APP_NAME}_experiment_summary.csv"
LOCUST_RESULTS_DIR = TMP_PATH / "locust" / APP_NAME
LOCUST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Experiment:
    workload_name: str
    autoscaler_name: str
    config: dict[str, Any]
    deployment_names: list[str] | None = None

    @property
    def name(self) -> str:
        if self.autoscaler_name == "none":
            suffix = "none"
        elif self.autoscaler_name == "default_cpu":
            suffix = f"cpu{self.config.get('average_cpu_utilization', 'na')}"
        else:
            suffix = self.autoscaler_name

        scope = "all" if not self.deployment_names else "subset"
        return f"{CURRENT_APP['name_prefix']}_{self.workload_name}_{suffix}_{scope}"


def get_workload_csv(workload_name: str) -> str:
    return f"{CURRENT_APP['workload_dir']}/{workload_name}.csv"


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
            "app",
            "experiment_name",
            "workload_name",
            "workload_csv",
            "autoscaler_name",
            "deployment_scope",
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
    locust_files: dict[str, Any] | None,
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
            APP_NAME,
            exp.name,
            exp.workload_name,
            get_workload_csv(exp.workload_name),
            exp.autoscaler_name,
            "all" if not exp.deployment_names else ",".join(exp.deployment_names),
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
        "app": APP_NAME,
        "namespace": NAMESPACE,
        "workload_name": exp.workload_name,
        "duration_seconds": DURATION_SECONDS,
        "autoscaler": {
            "autoscaler_name": exp.autoscaler_name,
            "config": exp.config,
        },
        "monitor": {
            "interval": MONITOR_INTERVAL,
            "prom_url": PROM_URL,
            "file_prefix": f"{APP_NAME}_mesh_metrics",
        },
    }

    if exp.deployment_names:
        payload["autoscaler"]["deployment_names"] = exp.deployment_names

    print(f"[SETUP] {exp.name}")
    result = post_json(f"{SERVER_BASE_URL}/experiment/setup", payload)
    print(json.dumps(result, indent=2))
    return result


def cleanup_experiment(exp: Experiment) -> dict[str, Any]:
    payload = {
        "app": APP_NAME,
        "namespace": NAMESPACE,
        "autoscaler_name": exp.autoscaler_name,
        "delete_autoscaler": exp.autoscaler_name != "none",
        "stop_monitoring": True,
    }

    if exp.deployment_names:
        payload["deployment_names"] = exp.deployment_names

    print(f"[CLEANUP] {exp.name}")
    result = post_json(f"{SERVER_BASE_URL}/experiment/cleanup", payload)
    print(json.dumps(result, indent=2))
    return result


def run_locust(exp: Experiment) -> dict[str, Any]:
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = LOCUST_RESULTS_DIR / f"{exp.name}_{timestamp}"
    csv_path = get_workload_csv(exp.workload_name)

    host = CURRENT_APP["host"]
    if not host:
        raise RuntimeError(f"No host configured for app={APP_NAME}")

    locust_file = CURRENT_APP["locust_file"]

    cmd = [
        "locust",
        "-f",
        locust_file,
        "--headless",
        "--host",
        host,
        "--csv",
        str(prefix),
        "--only-summary",
    ]

    env = os.environ.copy()
    env["APP_NAME"] = APP_NAME
    env["CSV_PATH"] = csv_path
    env["TIME_MINUTE"] = str(max(1, DURATION_SECONDS // 60))
    env["SPAWN_RATE"] = os.getenv("SPAWN_RATE", "20")
    env["SCALE_FACTOR"] = os.getenv("SCALE_FACTOR", "1")

    print("[LOCUST CMD]")
    print(" ".join(cmd))
    print(f"[APP] {APP_NAME}")
    print(f"[HOST] {host}")
    print(f"[WORKLOAD] {csv_path}")

    result = subprocess.run(cmd, check=False, env=env)
    print(f"[LOCUST EXIT CODE] {result.returncode}")

    return {
        "exit_code": result.returncode,
        "stats_csv": f"{prefix}_stats.csv",
        "failures_csv": f"{prefix}_failures.csv",
        "exceptions_csv": f"{prefix}_exceptions.csv",
        "stats_history_csv": f"{prefix}_stats_history.csv",
    }


def build_experiments() -> list[Experiment]:
    experiments: list[Experiment] = []

    for workload_name, autoscaler in itertools.product(WORKLOAD_NAME, AUTOSCALER_SETTINGS):
        experiments.append(
            Experiment(
                workload_name=workload_name,
                autoscaler_name=autoscaler["autoscaler_name"],
                config=autoscaler.get("config", {}),
                deployment_names=autoscaler.get("deployment_names"),
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
    print(f"[APP] {APP_NAME}")
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
