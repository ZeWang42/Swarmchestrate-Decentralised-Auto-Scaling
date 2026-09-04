import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

# Enforce order: HPA → DAS → Queue
files = {
    "HPA-80": ["HPA-80-1.csv", "HPA-80-2.csv"],
    "DAS": ["DAS-1.csv", "DAS-2.csv"],
    "Queue-DAS": ["our-queue-das-1.csv", "our-queue-das-2.csv"],
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
# STEP 2: minute bins
# -----------------------------------
per_second["Minute"] = per_second["ElapsedSec"] // 60

# -----------------------------------
# STEP 3: average per second within minute
# -----------------------------------
per_minute = (
    per_second
    .groupby(["Scheme", "Run", "Minute"], as_index=False)["AllocatedCPU"]
    .mean()
)

# -----------------------------------
# STEP 4: average across runs
# -----------------------------------
final = (
    per_minute
    .groupby(["Scheme", "Minute"], as_index=False)["AllocatedCPU"]
    .mean()
)

# -----------------------------------
# PLOT
# -----------------------------------
plt.figure(figsize=(10, 5))

for scheme, color in zip(files.keys(), colors):
    s = final[final["Scheme"] == scheme]
    plt.plot(
        s["Minute"],
        s["AllocatedCPU"],
        marker="o",
        linewidth=2,
        color=color,
        label=scheme
    )

plt.xlabel("Time (minutes)")
plt.ylabel("Allocated CPU (cores)")
plt.title("Allocated CPU over time (per-minute, avg per-second)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("deployment_cpu_allocation_line.png", dpi=300)
plt.show()
