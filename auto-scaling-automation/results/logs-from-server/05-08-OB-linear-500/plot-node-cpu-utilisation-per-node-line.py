import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

DATA_DIR = Path(".")

# Enforce order: HPA → DAS → Queue
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
        df = df[df["Scope"] == "node"].copy()

        start_time = df["Timestamp"].min()
        df["ElapsedSec"] = (df["Timestamp"] - start_time).dt.total_seconds().astype(int)

        df["Scheme"] = scheme
        df["Run"] = run_id

        all_data.append(df)

data = pd.concat(all_data, ignore_index=True)

# -----------------------------------
# STEP 1: per-second per-node values
# -----------------------------------
per_second = (
    data
    .groupby(["Scheme", "Run", "Name", "ElapsedSec"], as_index=False)["CPU_pct"]
    .mean()
)

# -----------------------------------
# STEP 2: minute bins
# -----------------------------------
per_second["Minute"] = per_second["ElapsedSec"] // 60

# -----------------------------------
# STEP 3: average per-second within minute
# -----------------------------------
per_minute = (
    per_second
    .groupby(["Scheme", "Run", "Name", "Minute"], as_index=False)["CPU_pct"]
    .mean()
)

# -----------------------------------
# STEP 4: average across runs
# -----------------------------------
final = (
    per_minute
    .groupby(["Scheme", "Name", "Minute"], as_index=False)["CPU_pct"]
    .mean()
)

# -----------------------------------
# PLOTTING
# -----------------------------------
nodes = sorted(final["Name"].unique())

for node in nodes:
    plt.figure(figsize=(10, 5))

    subset = final[final["Name"] == node]

    for scheme, color in zip(files.keys(), colors):
        s = subset[subset["Scheme"] == scheme]
        plt.plot(
            s["Minute"],
            s["CPU_pct"],
            marker="o",
            linewidth=2,
            color=color,
            label=scheme
        )

    plt.xlabel("Time (minutes)")
    plt.ylabel("CPU utilization (%)")
    plt.title(f"Node CPU utilization - {node}")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"node_{node}_cpu_utilisation_line.png", dpi=300)
    plt.show()
