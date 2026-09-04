import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

files = {
    "HPA-80": ["hpa-80-1.csv","hpa-80-2.csv"],
    "Custom-DAS": ["custom-das-1.csv", "custom-das-2.csv"],
    "DAS": ["das-1.csv", "das-2.csv"],
}

colors = {
    "Pods": "tab:blue",
    "P95": "tab:red",
}

all_pods = []
all_p95 = []

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        df = pd.read_csv(DATA_DIR / file)
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (df["Timestamp"] - start_time).dt.total_seconds().astype(int)
        df["Minute"] = df["ElapsedSec"] // 60
        df["Scheme"] = scheme
        df["Run"] = run_id

        # -------------------------
        # Pod count: deployment rows
        # -------------------------
        pods = df[df["Scope"] == "deployment"].copy()

        pods_per_second = (
            pods
            .groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)["Pods"]
            .sum()
        )

        pods_per_second["Minute"] = pods_per_second["ElapsedSec"] // 60

        pods_per_minute = (
            pods_per_second
            .groupby(["Scheme", "Run", "Minute"], as_index=False)["Pods"]
            .mean()
        )

        all_pods.append(pods_per_minute)

        # -------------------------
        # P95 latency rows
        # -------------------------
        latency_col = "HTTP_LAT_ms"

        p95 = df[
            (df["Scope"] == "http_p95_latency") &
            (df[latency_col].notna())
        ].copy()

        p95_per_minute = (
            p95
            .groupby(["Scheme", "Run", "Minute"], as_index=False)[latency_col]
            .mean()
        )

        all_p95.append(p95_per_minute)


pods_data = pd.concat(all_pods, ignore_index=True)
p95_data = pd.concat(all_p95, ignore_index=True)

pods_final = (
    pods_data
    .groupby(["Scheme", "Minute"], as_index=False)["Pods"]
    .mean()
)

p95_final = (
    p95_data
    .groupby(["Scheme", "Minute"], as_index=False)["HTTP_LAT_ms"]
    .mean()
)

# -------------------------
# One plot per scheme
# -------------------------
for scheme in files.keys():
    s_pods = pods_final[pods_final["Scheme"] == scheme]
    s_p95 = p95_final[p95_final["Scheme"] == scheme]

    fig, ax1 = plt.subplots(figsize=(10, 5))

    ax1.plot(
        s_pods["Minute"],
        s_pods["Pods"],
        marker="o",
        linewidth=2,
        color=colors["Pods"],
        label="Average #Pods"
    )

    ax1.set_xlabel("Time (minutes)")
    ax1.set_ylabel("Average #Pods", color=colors["Pods"])
    ax1.tick_params(axis="y", labelcolor=colors["Pods"])
    ax1.set_ylim(0, 50)     # Pods axis
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()

    ax2.plot(
        s_p95["Minute"],
        s_p95["HTTP_LAT_ms"],
        marker="s",
        linewidth=2,
        color=colors["P95"],
        label="P95 latency"
    )
    ax2.axhline(
        y=500,
        color="black",
        linestyle="--",
        linewidth=2,
    )

    ax2.text(
        s_p95["Minute"].max(),
        500,
        "500 ms SLO",
        ha="right",
        va="bottom",
        fontsize=10,
        color="black",
    )
    ax2.set_ylabel("P95 latency (ms)", color=colors["P95"])
    ax2.tick_params(axis="y", labelcolor=colors["P95"])
    ax2.set_ylim(0, 1000)    # Latency axis


    plt.title(f"{scheme}: pod count and p95 latency per minute")

    fig.tight_layout()
    plt.savefig(f"{scheme.lower().replace('-', '_')}_pods_p95_latency.png", dpi=300)
    plt.show()
