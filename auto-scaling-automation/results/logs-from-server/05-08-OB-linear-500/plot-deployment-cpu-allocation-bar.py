import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

# Order matters here → HPA, DAS, Queue
files = {
    "HPA-80": ["hpa-80.csv"],
    "DAS": ["das.csv"],
    "Queue-DAS": ["queue-das.csv"],
}
colors = ["tab:blue", "tab:orange", "tab:green"]

all_data = []

for scheme, file_list in files.items():
    for run_id, file in enumerate(file_list, start=1):
        df = pd.read_csv(DATA_DIR / file)

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df[df["Scope"] == "deployment"].copy()

        df["CPU_request"] = df["Name"].apply(
            lambda x: 0.2 if x == "productpage-v1" else 0.1
        )

        df["AllocatedCPU"] = df["Pods"] * df["CPU_request"]

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (df["Timestamp"] - start_time).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

# -----------------------------------
# STEP 1: total allocated CPU per second
# -----------------------------------
per_second = (
    data
    .groupby(["Scheme", "Run", "ElapsedSec"], as_index=False)["AllocatedCPU"]
    .sum()
)

# -----------------------------------
# STEP 2: accumulated CPU-seconds per run
# -----------------------------------
run_totals = (
    per_second
    .groupby(["Scheme", "Run"], as_index=False)["AllocatedCPU"]
    .sum()
)

run_totals = run_totals.rename(columns={"AllocatedCPU": "CPU_seconds"})

# -----------------------------------
# STEP 3: average across runs
# -----------------------------------
final = (
    run_totals
    .groupby("Scheme", as_index=False)["CPU_seconds"]
    .mean()
)

# Enforce order: HPA → DAS → Queue
final = final.set_index("Scheme").loc[files.keys()].reset_index()

# -----------------------------------
# PLOT
# -----------------------------------
plt.figure(figsize=(7, 5))

bars = plt.bar(
    final["Scheme"],
    final["CPU_seconds"],
    color=colors
)

# Add value labels on top of bars
for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height * 1.01,
        f"{height:.0f}",
        ha="center",
        va="bottom",
        fontsize=10
    )

plt.xlabel("Scheme")
plt.ylabel("Accumulated allocated CPU (CPU-seconds)")
plt.title("Accumulated allocated CPU of all deployments")

plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_cpu_allocation_bar.png", dpi=300)
plt.show()
